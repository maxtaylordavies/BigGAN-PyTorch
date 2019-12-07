#PBS -l walltime=01:00:00,select=1:ncpus=1:mem=16gb:ngpus=1

module load anaconda3/personal
source activate biggan
cd $PBS_O_WORKDIR

#python make_hdf5.py --dataset SWET_ERYTHEMA --batch_size 256
python calculate_inception_moments.py --dataset SWET_ERYTHEMA_hdf5
