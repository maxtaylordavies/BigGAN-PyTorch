import numpy as np
import math
import functools

import torch
import torch.nn as nn
from torch.nn import init
import torch.optim as optim
import torch.nn.functional as F
from torch.nn import Parameter as P

import layers
                   

# Architectures for G
# New strategy: pass in attention values as G_attn='64_128' then
# attention[int(item)] = True for item in G_attn.split('_')
def G_arch(ch=64, attention='64', ksize='333333', dilation='111111'):
  arch = {}
  arch[256] = {'in_channels' :  [ch * item for item in [16, 16, 8, 8, 4, 2]],
               'out_channels' : [ch * item for item in [16,  8, 8, 4, 2, 1]],
               'upsample' : [True] * 6,
               'resolution' : [8, 16, 32, 64, 128, 256],
               'attention' : {2**i: (2**i in [int(item) for item in attention.split('_')])
                              for i in range(3,9)}}
  arch[128] = {'in_channels' :  [ch * item for item in [16, 16, 8, 4, 2]],
               'out_channels' : [ch * item for item in [16, 8, 4, 2, 1]],
               'upsample' : [True] * 5,
               'resolution' : [8, 16, 32, 64, 128],
               'attention' : {2**i: (2**i in [int(item) for item in attention.split('_')])
                              for i in range(3,8)}}
  arch[64]  = {'in_channels' :  [ch * item for item in [16, 16, 8, 4]],
               'out_channels' : [ch * item for item in [16, 8, 4, 2]],
               'upsample' : [True] * 4,
               'resolution' : [8, 16, 32, 64],
               'attention' : {2**i: (2**i in [int(item) for item in attention.split('_')])
                              for i in range(3,7)}} 
  arch[32]  = {'in_channels' :  [ch * item for item in [4, 4, 4]],
               'out_channels' : [ch * item for item in [4, 4, 4]],
               'upsample' : [True] * 3,
               'resolution' : [8, 16, 32],
               'attention' : {2**i: (2**i in [int(item) for item in attention.split('_')])
                              for i in range(3,6)}}

  return arch

class Generator(nn.Module):
  def __init__(self, G_ch=64, dim_z=128, bottom_width=4, resolution=128,
               G_kernel_size=3, G_attn='64', n_classes=1000,
               num_G_SVs=1, num_G_SV_itrs=1,
               G_shared=True, shared_dim=None, hier=False,
               cross_replica=False,
               G_activation=nn.ReLU(inplace=False), 
               G_lr=5e-5, G_B1=0.0, G_B2=0.999,
               G_init='ortho', G_param='SN', norm_style='bn',
               **kwargs):          
    super(Generator, self).__init__()
    # Channel width mulitplier
    self.ch = G_ch
    # Dimensionality of the latent space
    self.dim_z = dim_z
    # The initial spatial dimensions
    self.bottom_width = bottom_width
    # Resolution of the output
    self.resolution = resolution
    # Kernel size?
    self.kernel_size = G_kernel_size
    # Attention?
    self.attention = G_attn
    # number of classes, for use in categorical conditional generation
    self.n_classes = n_classes
    # Use shared embeddings?
    self.G_shared = G_shared
    # Dimensionality of the shared embedding? Unused if not using G_shared      
    self.shared_dim = shared_dim if shared_dim else dim_z
    # Hierarchical latent space?
    self.hier = hier
    # Cross replica batchnorm?
    self.cross_replica = cross_replica
    # nonlinearity for residual blocks
    self.activation = G_activation
    # Initialization style
    self.init = G_init
    # Parameterization style
    self.G_param = G_param
    # Normalization style
    self.norm_style = norm_style
    
    # Architecture dict
    self.arch = G_arch(self.ch, self.attention)[resolution]
    
    # If using hierarchical latents, adjust z
    if self.hier:
      self.num_slots = len(self.arch['in_channels']) + 1 # Number of places z slots into
      self.z_chunk_size = (self.dim_z // self.num_slots)
      self.dim_z = self.z_chunk_size *  self.num_slots # Recalculate latent dimensionality for even splitting into chunks
    else:
      self.num_slots = 1
      self.z_chunk_size = 0
    
    # Which convs, batchnorms, and linear layers to use
    if self.G_param == 'SN':
      self.which_conv = functools.partial(layers.SNConv2d,
                          kernel_size=3, padding=1,
                          num_svs=num_G_SVs, num_itrs=num_G_SV_itrs)
      self.which_linear = functools.partial(layers.SNLinear,
                          num_svs=num_G_SVs, num_itrs=num_G_SV_itrs)
      self.which_embedding = functools.partial(layers.SNEmbedding,
                              num_svs=num_G_SVs, num_itrs=num_G_SV_itrs)
    else:
      self.which_conv = functools.partial(nn.Conv2d, kernel_size=3, padding=1)
      self.which_linear = nn.Linear
      self.which_embedding = nn.Embedding
      
    bn_linear = functools.partial(self.which_linear, bias=False) if self.G_shared else self.which_embedding
    self.which_bn = functools.partial(layers.ccbn,
                          which_linear=bn_linear,
                          cross_replica=self.cross_replica,
                          input_size=self.shared_dim + self.z_chunk_size if self.G_shared else self.n_classes,
                          norm_style=self.norm_style)
    
    
    # Prepare model
    # If not using shared embeddings, self.shared is just a passthrough
    self.shared = self.which_embedding(n_classes, self.shared_dim) if G_shared else layers.identity()
    # First linear layer
    self.linear = self.which_linear(self.dim_z // self.num_slots, 
                                    self.arch['in_channels'][0] * (self.bottom_width **2))
    
    # self.blocks is a doubly-nested list of modules, the outer loop intended
    # to be over blocks at a given resolution (resblocks and/or self-attention)
    self.blocks = []
    for index in range(len(self.arch['out_channels'])):
      self.blocks += [[layers.GBlock(in_channels=self.arch['in_channels'][index],
                             out_channels=self.arch['out_channels'][index],
                             which_conv=self.which_conv,
                             which_bn=self.which_bn,
                             activation=self.activation,
                             upsample=(functools.partial(F.interpolate, scale_factor=2)
                                       if self.arch['upsample'][index] else None))]]
      
      # If attention on this block, attach it to the end
      if self.arch['attention'][self.arch['resolution'][index]]:
        print('Adding attention layer in G at resolution %d' % self.arch['resolution'][index])
        self.blocks[-1] += [layers.Attention(self.arch['out_channels'][index], self.which_conv)]
                   
    # Turn self.blocks into a ModuleList so that it's all properly registered.
    self.blocks = nn.ModuleList([nn.ModuleList(block) for block in self.blocks])
  
    # output layer: batchnorm-relu-conv. Optionally use an nn.BatchNorm2d, or
    # use a non-spectral conv, by toggling these comments.
    self.output_layer = nn.Sequential(layers.bn(self.arch['out_channels'][-1],
                                                cross_replica=self.cross_replica),
                                    # nn.BatchNorm2d(self.arch['out_channels'][-1] * self.ch,affine=True),
                                    self.activation,
                                    #nn.Conv2d(self.arch['out_channels'][-1] * self.ch, 3, 3,padding=1))
                                    self.which_conv(self.arch['out_channels'][-1], 3)) # Consider using a non-spectral conv here
    
    # Initialize weights
    self.init_weights()
    
    # Set up optimizer
    self.lr, self.B1, self.B2 = G_lr, G_B1, G_B2
    self.optim = optim.Adam(params=self.parameters(), lr=self.lr,
                           betas=(self.B1, self.B2), weight_decay=0)
    
    # LR scheduling, left here for forward compatibility
    # self.lr_sched = {'itr' : 0}# if self.progressive else {}
    # self.j = 0
  
  # Initialize
  def init_weights(self):    
    # print('Skipping initialization for now...')
    self.param_count = 0
    for module in self.modules():
      if isinstance(module, nn.Conv2d) or isinstance(module, nn.Linear):
        # pass # Uncomment this to skip init step on convs and linears
        if self.init == 'ortho':
          init.orthogonal_(module.weight)       
        elif self.init == 'N02':
          init.normal_(module.weight, 0, 0.02)
        elif self.init in ['glorot', 'xavier']:
          init.xavier_uniform_(module.weight)
        else:
          print('Init style not recognized...')
        self.param_count += sum([p.data.nelement() for p in module.parameters()])
      # Regardless of init style, init embeding with N(0, 0.02)  
      elif isinstance(module, nn.Embedding):
        init.normal_(module.weight, 0, 0.02)
        self.param_count += sum([p.data.nelement() for p in module.parameters()])
      #else:
        #print(type(module))
    print('Param count for G''s initialized parameters: %d' % self.param_count)

  # Notes on this forward function: we pass in a y vector which has
  # already been passed through G.shared to enable easy class-wise
  # interpolation later. If we passed in the one-hot and then ran it through
  # G.shared in this forward function, it would be harder to handle.
  def forward(self, z, y):
  
    # If hierarchical, concatenate zs and ys
    if self.hier:
      zs = torch.split(z, self.z_chunk_size, 1)
      z = zs[0]
      ys = [torch.cat([y, item], 1) for item in zs[1:]]
    else:
      ys = [y] * len(self.blocks)
    # First linear layer
    h = self.linear(z)
    # Reshape
    h = h.view(h.size(0), -1, self.bottom_width, self.bottom_width)
    # Loop over blocks
    for index, blocklist in enumerate(self.blocks):
      # Second inner loop in case block has multiple layers
      for block in blocklist:
        h = block(h, ys[index])
    # Apply batchnorm-relu-conv-tanh at output
    return torch.tanh(self.output_layer(h))


# Discriminator
def D_arch(ch=64, attention='64',ksize='333333', dilation='111111'):
  arch = {}
  arch[256] = {'in_channels' :  [3] + [ch*item for item in [1, 2, 4, 8, 8, 16]],
               'out_channels' : [item * ch for item in [1, 2, 4, 8, 8, 16, 16]],
               'downsample' : [True] * 6 + [False],
               'resolution' : [128, 64, 32, 16, 8, 4, 4 ],
               'attention' : {2**i: 2**i in [int(item) for item in attention.split('_')] 
                              for i in range(2,8)}}
  arch[128] = {'in_channels' :  [3] + [ch*item for item in [1, 2, 4, 8, 16]],
               'out_channels' : [item * ch for item in [1, 2, 4, 8, 16, 16]],
               'downsample' : [True] * 5 + [False],
               'resolution' : [64, 32, 16, 8, 4, 4],
               'attention' : {2**i: 2**i in [int(item) for item in attention.split('_')] 
                              for i in range(2,8)}}
  arch[64]  = {'in_channels' :  [3] + [ch*item for item in [1, 2, 4, 8]],
               'out_channels' : [item * ch for item in [1, 2, 4, 8, 16]],
               'downsample' : [True] * 4 + [False],
               'resolution' : [32, 16, 8, 4, 4],
               'attention' : {2**i: 2**i in [int(item) for item in attention.split('_')] 
                              for i in range(2,7)}}
  arch[32]  = {'in_channels' :  [3] + [item * ch for item in [4, 4, 4]],
               'out_channels' : [item * ch for item in [4, 4, 4, 4]],
               'downsample' : [True, True, False, False],
               'resolution' : [16, 16, 16, 16],
               'attention' : {2**i: 2**i in [int(item) for item in attention.split('_')] 
                              for i in range(2,6)}}
  return arch
  
# DBlock for SN-GAN, different channel pattern
class SNGAN_DBlock(nn.Module):
  def __init__(self, in_channels, out_channels, which_conv=layers.SNConv2d,
               preactivation=False, activation=None, downsample=None):
    super(SNGAN_DBlock, self).__init__()
    self.in_channels, self.out_channels = in_channels, out_channels
    self.which_conv = which_conv
    self.preactivation = preactivation
    self.hidden_channels = self.in_channels if self.preactivation else self.out_channels
    self.activation = activation
    self.downsample = downsample
        
    # Conv layers
    self.conv1 = self.which_conv(self.in_channels, self.hidden_channels)
    self.conv2 = self.which_conv(self.hidden_channels, self.out_channels)
    self.learnable_sc = (in_channels != out_channels) or downsample
    if self.learnable_sc:
      self.conv_sc = self.which_conv(in_channels, out_channels, 
                                     kernel_size=1, padding=0)
  def shortcut(self, x):
    if self.preactivation:
      if self.learnable_sc:
        x = self.conv_sc(x)
      if self.downsample:
        x = self.downsample(x)
    else:
      if self.downsample:
        x = self.downsample(x)
      if self.learnable_sc:
        x = self.conv_sc(x)
    return x
    
  def forward(self, x):
    if self.preactivation:
      h = self.activation(x)      
    else:
      h = x    
    h = self.conv1(h)
    h = self.conv2(self.activation(h))      
    """ HEY ANDY THIS MAY BE WRONG WE DOWN DS-CONV ON X BUT IT MAY NEED TO BE CONV-DS"""
    if self.downsample:
      h = self.downsample(h)     
        
    return h + self.shortcut(x)
    
class Discriminator(nn.Module):

  def __init__(self, D_ch=64, resolution=128,
               D_kernel_size=3, D_attn='64', n_classes=1000,
               num_D_SVs=1, num_D_SV_itrs=1, D_activation=nn.ReLU(inplace=False),
               D_lr=2e-4, D_B1=0.0, D_B2=0.999,
               D_param='SN', output_dim=1,
               D_init='ortho', **kwargs):
    super(Discriminator, self).__init__()
    # Width multiplier
    self.ch = D_ch
    # Resolution
    self.resolution = resolution
    # Kernel size
    self.kernel_size = D_kernel_size
    # Attention?
    self.attention = D_attn
    # Number of classes
    self.n_classes = n_classes
    # Activation
    self.activation = D_activation
    # Initialization style
    self.init = D_init
    # Architecture
    self.arch = D_arch(self.ch, self.attention)[resolution]
    
    # Which convs, batchnorms, and linear layers to use
    # No option to turn off SN in D right now
    if D_param == 'SN':
      self.which_conv = functools.partial(layers.SNConv2d,
                          kernel_size=3, padding=1,
                          num_svs=num_D_SVs, num_itrs=num_D_SV_itrs)
      self.which_linear = functools.partial(layers.SNLinear,
                          num_svs=num_D_SVs, num_itrs=num_D_SV_itrs)
      self.which_embedding = functools.partial(layers.SNEmbedding,
                              num_svs=num_D_SVs, num_itrs=num_D_SV_itrs)

    
    # Prepare model
    # self.blocks is a doubly-nested list of modules, the outer loop intended
    # to be over blocks at a given resolution (resblocks and/or self-attention)

    self.blocks = []
    for index in range(len(self.arch['out_channels'])):
      self.blocks += [[SNGAN_DBlock(in_channels=self.arch['in_channels'][index],
                       out_channels=self.arch['out_channels'][index],
                       which_conv=self.which_conv,
                       activation=self.activation,
                       preactivation=(index > 0),
                       downsample=(nn.AvgPool2d(2) if self.arch['downsample'][index] else None))]]
      # If attention on this block, attach it to the end
      if self.arch['attention'][self.arch['resolution'][index]]:
        print('Adding attention layer in D at resolution %d' % self.arch['resolution'][index])
        self.blocks[-1] += [layers.Attention(self.arch['out_channels'][index],
                                             self.which_conv)]
    # Turn self.blocks into a ModuleList so that it's all properly registered.   
    self.blocks = nn.ModuleList([nn.ModuleList(block) for block in self.blocks])
    # Linear output layer. The output dimension is typically 1, but may be
    # larger if we're e.g. turning this into a VAE with an inference output
    self.linear = self.which_linear(self.arch['out_channels'][-1], output_dim)
    # Embedding for projection discrimination
    self.embed = self.which_embedding(self.n_classes, self.arch['out_channels'][-1])
    
    # Initialize weights
    self.init_weights()
    
    # Set up optimizer
    self.lr, self.B1, self.B2 = D_lr, D_B1, D_B2
    self.optim = optim.Adam(params=self.parameters(), lr=self.lr,
                           betas=(D_B1, D_B2), weight_decay=0)
    # LR scheduling, left here for forward compatibility
    # self.lr_sched = {'itr' : 0}# if self.progressive else {}
    # self.j = 0 
  
  # Initialize
  def init_weights(self):    
    # print('Skipping initialization for now...')
    self.param_count = 0
    for module in self.modules():
      if isinstance(module, nn.Conv2d) or isinstance(module, nn.Linear):
        # pass # Uncomment this to skip init step on convs and linears
        if self.init == 'ortho':
          init.orthogonal_(module.weight)          
        elif self.init == 'N02':
          init.normal_(module.weight, 0, 0.02)
        elif self.init in ['glorot', 'xavier']:
          init.xavier_uniform_(module.weight)
        else:
          print('Init style not recognized...')
        self.param_count += sum([p.data.nelement() for p in module.parameters()])
      # Regardless of init style, init embeding with N(0, 0.02)
      elif isinstance(module, nn.Embedding):
        init.normal_(module.weight, 0, 0.02)
        self.param_count += sum([p.data.nelement() for p in module.parameters()])
      #else:
        #print(type(module))
    print('Param count for D''s initialized parameters: %d' % self.param_count)
    
  def forward(self, x, y=None):
    # Stick x into h for cleaner for loops without flow control
    h = x
    # Loop over blocks
    for index, blocklist in enumerate(self.blocks):
      for block in blocklist:
        h = block(h)
    # Apply global sum pooling as in SN-GAN
    h = torch.sum(self.activation(h), [2, 3])
    # Get initial class-unconditional output
    out = self.linear(h)
    # Get projection of final featureset onto class vectors and add to evidence
    out = out + torch.sum(self.embed(y) * h, 1, keepdim=True)      
    return out
    
# Parallelized G_D to minimize cross-gpu communication
# Without this, Generator outputs would get all-gathered and then rebroadcast.
class G_D(nn.Module):
  def __init__(self, G, D):
    super(G_D, self).__init__()
    self.G = G
    self.D = D
    
  def forward(self, z, gy, x=None, dy=None, train_G=False, return_G_z=False,
              split_D=False):
    # If training G, enable grad
    with torch.set_grad_enabled(train_G):
      # Get Generator output given noise
      G_z = self.G(z, self.G.shared(gy))
    
    # Split_D means to run D once with real data and once with fake,
    # rather than concatenating along the batch dimension
    if split_D:
      D_fake = self.D(G_z, gy)
      if x is not None:
        D_real = self.D(x, dy)
        return D_fake, D_real
      else:
        if return_G_z:
          return D_fake, G_z
        else:
          return D_fake
    # If real data is provided, concatenate it with the Generator's output
    # along the batch dimension for improved efficiency.
    else:
      D_input = torch.cat([G_z, x], 0) if x is not None else G_z
      D_class = torch.cat([gy, dy], 0) if dy is not None else gy
      # Get Discriminator output
      D_out = self.D(D_input, D_class)
      if x is not None:
        return torch.split(D_out, [G_z.shape[0], x.shape[0]]) # D_fake, D_real 
      else:
        if return_G_z:
          return D_out, G_z
        else:
          return D_out
