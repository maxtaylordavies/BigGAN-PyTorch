import pandas as pd
import sys
import os
from argparse import ArgumentParser
from shutil import copyfile


def prepare_parser():
    parser = ArgumentParser()
    parser.add_argument(
        '--source_path', type=str, default='/Users/maxtaylordavies/project/swet_images_auto_crops',
        help='path to autocrop data directory from EczemaNet repo')
    parser.add_argument(
        '--dest_path', type=str, default='/Users/maxtaylordavies/project/BigGAN-PyTorch/data/swet_erythema',
        help='path to where we want to put our data in the BigGAN repo')
    parser.add_argument(
        '--labels_csv_path', type=str, default='/Users/maxtaylordavies/project/repsites_scores_TISS+SASSAD.csv',
        help='path to csv file from EczemaNet repo with severity scores')
    return parser


def main():
    parser = prepare_parser()
    config = vars(parser.parse_args())

    labels_df = pd.read_csv(config["labels_csv_path"])
    labels_dict = {0: "none", 1: "mild", 2: "moderate", 3: "severe"}

    for label_name in labels_dict.values():
        d = os.path.join(config['dest_path'], label_name)
        if not os.path.exists(d):
            os.makedirs(d)

    files = []
    for (_, _, filenames) in os.walk(config['source_path']):
        files += filenames

    for f in files:
        refno = int(f.split("_")[0])
        visno = int(f.split("_")[1])
        df_row = labels_df[(labels_df["refno"] == refno) & (labels_df["visno"] == visno)]

        label_name = labels_dict[df_row['tiss_ery'].values[0]]
        copyfile(os.path.join(config["source_path"], f), os.path.join(config["dest_path"], label_name, f))


if __name__ == '__main__':
    main()
