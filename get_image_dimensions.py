from PIL import Image
import os
import matplotlib.pyplot as plt
import numpy as np

def getDimensions(root, labels):
    dimensions = {l:[] for l in labels}
    for label in labels:
        for (_, _, filenames) in os.walk(os.path.join(root, label)):
            for f in filenames:
                im = Image.open(os.path.join(root, label, f))
                width, height = im.size
                dimensions[label].append(min(width, height))
    return dimensions

def plotDimensions(dimensions):
    data = [np.asarray(dim) for dim in list(dimensions.values())]
    weights = []
    for dim in data:
        w = np.empty(dim.shape)
        w.fill(1/dim.shape[0])
        weights.append(w)

    plt.hist(data, 20, weights=weights, label=['none', 'mild', 'moderate', 'severe'], color=['darkgreen', 'mediumseagreen', 'teal', 'midnightblue'])
    plt.title("Histogram of limiting image dimensions")
    plt.legend(loc='upper right')
    plt.grid(True)

    plt.show()

def main():
    root = "/Users/maxtaylordavies/project/BigGAN-PyTorch/data/swet_erythema"
    labels = ["none", "mild", "moderate", "severe"]
    dimensions = getDimensions(root, labels)
    plotDimensions(dimensions)

if __name__ == "__main__":
    main()