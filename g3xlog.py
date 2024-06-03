#!/usr/bin/env python3

import glob
import re
import os
import pandas
import subprocess

def main():
    # Destination path
    log_path = "/Volumes/volume0/rv/data_log"
    
    # Create subfolders
    os.makedirs(log_path + "/config", exist_ok=True)
    os.makedirs(log_path + "/flight", exist_ok=True)
    os.makedirs(log_path + "/taxi", exist_ok=True)

    # Determine source path
    mount_root = "/Volumes"
    src_logs = []

    # Search filesystem for mounts that contain g3x logs
    mounts = glob.glob(mount_root + "/*")
    for mount in mounts:
        dirs = glob.glob(mount + "/*")
        for dir in dirs:
            if "data_log" in dir:
                logs = glob.glob(dir + "/*.csv")
                src_logs.extend(logs)

    # Process each log source
    for log in src_logs:

        # Read first line in file (metadata)
        with open(log, "r") as file:
            first_line = file.readline()

        # Comma separated
        metadata_text = first_line.strip().split(",")
    
        # Verify first item
        if metadata_text[0] != "#airframe_info":
            raise ValueError("Not a Garmin G3X log file")

        # Convert the rest to dict
        metadata = dict(map(lambda meta: re.fullmatch("(.*)=\"(.*)\"", meta).groups(), metadata_text[1:]))

        # Parse CSV
        df = pandas.read_csv(log, skiprows=[0,2])
        
        # If file has zero data, recommend deleting
        if df.empty:
            print("empty: ", log)
        else:
            if df["Oil Press (PSI)"].max() < 1:
                dest_path = log_path + "/config/"
                print("config:", log)
            elif df["GPS Ground Speed (kt)"].max() < 50:
                dest_path = log_path + "/taxi/"
                print("taxi:  ", log)
            else:
                dest_path = log_path + "/flight/"
                print("flight:", log)

            subprocess.call(["rsync", "-t", "--ignore-existing", log, dest_path])

if __name__ == "__main__":
    """ This is executed when run from the command line """
    main()