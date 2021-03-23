# Import Statements
from __future__ import division

from microfaune_package.microfaune.detection import RNNDetector
from microfaune_package.microfaune import audio
import matplotlib.pyplot as plt
import os
from pathlib import Path
import sys
import numpy as np
import pdb
import csv
import argparse
from scipy.io import wavfile
from scipy import stats
import scipy.signal as scipy_signal
import pandas as pd
import math

# Gabriel's original moment-to-moment classification tool. Reworked to output
# a Pandas DataFrame.
# TODO rework isolate in a way that allows a user to input a dictionary that where they can modulate different
# parameters involved in Gabriel's algorithm. We can set the default of this dict to be what he originally chose for now.
# Some ideas for how to change the parameters are to allow for different modification of the threshold. We would want to be able
# to modify the bird presence threshold to be a pure value. This will allow us to build ROC curves. Another would be to allow for a
# selection of how many standard deviations away from the mean. Another would be, instead of a median, allow standard deviation and mean as
# alternatives. Another option would be to allow for curve smoothing on the local score array that is being passed in. This could come in
# the form of a high order polynomial fit or possibly testing out my curve smoothing algorithm that uses a bell-curved distribution to
# loop around and average each sample with its surrounding samples over many iterations. We could also play around with filtering.

# function that encapsulates many different isolation techniques to the dictionary isolation_parameters
def isolate(local_scores, SIGNAL, SAMPLE_RATE, audio_dir, filename,isolation_parameters,manual_id = "bird"):

    # initializing the output dataframe that will contain labels across a single clip
    isolation_df = pd.DataFrame()

    # deciding which isolation technique to deploy for a given clip
    if isolation_parameters["technique"] == "simple":
        isolation_df = simple_isolate(local_scores, SIGNAL, SAMPLE_RATE, audio_dir, filename, isolation_parameters,manual_id = "bird")
    elif isolation_parameters["technique"] == "steinberg":
        isolation_df = steinberg_isolate(local_scores, SIGNAL, SAMPLE_RATE, audio_dir, filename,isolation_parameters,manual_id = "bird")
#    elif isolation_parameters["technique"] == "stack"
    return isolation_df


def steinberg_isolate(local_scores, SIGNAL, SAMPLE_RATE, audio_dir, filename,isolation_parameters,manual_id = "bird"):
    # calculate original duration
    old_duration = len(SIGNAL) / SAMPLE_RATE

    # create entry for audio clip
    entry = {'FOLDER'  : audio_dir,
             'IN FILE'    : filename,
             'CHANNEL' : 0,
             'CLIP LENGTH': old_duration,
             'SAMPLE RATE': SAMPLE_RATE,
             'OFFSET'  : [],
             'MANUAL ID'  : []}

    # Variable to modulate when encapsulating this function.
    # treshold is 'thresh_mult' times above median score value
    # thresh_mult = 2
    if isolation_parameters["threshold_type"] == "median":
        thresh = np.median(local_scores) * isolation_parameters["threshold_const"]
    elif isolation_parameters["threshold_type"] == "mean" or isolation_parameters["threshold_type"] == "average":
        thresh = np.mean(local_scores) * isolation_parameters["threshold_const"]
    elif isolation_parameters["threshold_type"] == "standard deviation":
        thresh = np.std(local_scores) * isolation_parameters["threshold_const"]
    elif isolation_parameters["threshold_type"] == "pure" and (isolation_parameters["threshold_const"] < 0 or isolation_parameters["threshold_const"] > 1):
        print("A pure threshold must be between [0,1]")
        return
    elif isolation_parameters["threshold_type"] == "pure":
        thresh = isolation_parameters["threshold_const"]

    # how many samples one score represents
    # Scores meaning local scores
    samples_per_score = len(SIGNAL) // len(local_scores)

    # isolate samples that produce a score above thresh
    isolated_samples = np.empty(0, dtype=np.int16)
    prev_cap = 0        # sample idx of previously captured
    for i in range(len(local_scores)):
        # if a score hits or surpasses thresh, capture 1s on both sides of it
        if local_scores[i] >= thresh:
            # score_pos is the sample index that the score corresponds to
            score_pos = i * samples_per_score

            # upper and lower bound of captured call
            # sample rate is # of samples in 1 second: +-1 second
            lo_idx = max(0, score_pos - int(isolation_parameters["bi_directional_jump"]*SAMPLE_RATE))
            hi_idx = min(len(SIGNAL), score_pos + int(isolation_parameters["bi_directional_jump"]*SAMPLE_RATE))
            lo_time = lo_idx / SAMPLE_RATE
            hi_time = hi_idx / SAMPLE_RATE

            # calculate start and end stamps
            # create new sample if not overlapping or if first stamp
            if prev_cap < lo_idx or prev_cap == 0:
                # New label
                new_stamp = [lo_time, hi_time]
                # TODO make it so that here we get the duration
                entry['OFFSET'].append(new_stamp)
                entry['MANUAL ID'].append(manual_id)
            # extend same stamp if still overlapping
            else:
                entry['OFFSET'][-1][1] = hi_time

            # mark previously captured to prevent overlap collection
            lo_idx = max(prev_cap, lo_idx)
            prev_cap = hi_idx

            # add to isolated samples
            # sub-clip numpy array
            isolated_samples = np.append(isolated_samples,SIGNAL[lo_idx:hi_idx])


    entry = pd.DataFrame.from_dict(entry)
    # Making the necessary adjustments to the Pandas Dataframe so that it is compatible with Kaleidoscope.
    ## TODO, when you go through the process of rebuilding this isolate function as a potential optimization problem
    ## rework the algorithm so that it builds the dataframe correctly to save time.
    #print(entry["OFFSET"].tolist())
    # This solution is not system agnostic. The problem is that Gabriel stored the start and stop times as a list under the OFFSET column.
    OFFSET = entry['OFFSET'].str[0]
    DURATION = entry['OFFSET'].str[1]
    DURATION = DURATION - OFFSET
    # Adding a new "DURATION" Column
    # Making compatible with Kaleidoscope
    entry.insert(6,"DURATION",DURATION)
    entry["OFFSET"] = OFFSET
    return entry

def simple_isolate(local_scores, SIGNAL, SAMPLE_RATE, audio_dir, filename, isolation_parameters, manual_id = "bird"):
    #local_scores2 = local_scores
    #threshold = 2*np.median(local_scores)
    if isolation_parameters["threshold_type"] == "median":
        thresh = np.median(local_scores) * isolation_parameters["threshold_const"]
    elif isolation_parameters["threshold_type"] == "mean" or isolation_parameters["threshold_type"] == "average":
        thresh = np.mean(local_scores) * isolation_parameters["threshold_const"]
    elif isolation_parameters["threshold_type"] == "standard deviation":
        thresh = np.std(local_scores) * isolation_parameters["threshold_const"]
    elif isolation_parameters["threshold_type"] == "pure" and (isolation_parameters["threshold_const"] < 0 or isolation_parameters["threshold_const"] > 1):
        print("A pure threshold must be between [0,1]")
        return
    elif isolation_parameters["threshold_type"] == "pure":
        thresh = isolation_parameters["threshold_const"]

    # calculate original duration
    old_duration = len(SIGNAL) / SAMPLE_RATE

    entry = {'FOLDER'  : audio_dir,
             'IN FILE'    : filename,
             'CHANNEL' : 0,
             'CLIP LENGTH': old_duration,
             'SAMPLE RATE': SAMPLE_RATE,
             'OFFSET'  : [],
             'DURATION' : [],
             'MANUAL ID'  : []}

    # how many samples one score represents
    # Scores meaning local scores
    samples_per_score = len(SIGNAL) // len(local_scores)
    # local_score * samples_per_score / sample_rate
    time_per_score = samples_per_score / SAMPLE_RATE

    # setting scores above the threshold equal to one
    #local_scores2[local_scores2 >= threshold] = 1

    consecutive_samples = 0
    call_start = 0
    call_stop = 0
    # looping through all of the local scores
    for ndx in range(len(local_scores)):
        current_score = local_scores[ndx]
        # Start of a new sequence.
        if current_score >= thresh and consecutive_samples == 0:
            # signal a start of a new sequence.
            consecutive_samples = 1
            call_start = float(ndx*time_per_score)
            #print("Call Start",call_start)
        # End of a sequence
        elif current_score < thresh and consecutive_samples == 1:
            # signal the end of a sequence
            consecutive_samples = 0
            #
            call_end = float(ndx*time_per_score)
            #print("Call End",call_end)
            entry['OFFSET'].append(call_start)
            entry['DURATION'].append(call_end - call_start)
            entry['MANUAL ID'].append(manual_id)
            call_start = 0
            call_end = 0
        else:
            continue
    return pd.DataFrame.from_dict(entry)
    # implement this function after
#    def stack_isolate(local_scores, SIGNAL, SAMPLE_RATE, audio_dir, filename, threshold_type = "median", threshold_const = 2.0):




## Function that applies the moment to moment labeling system to a directory full of wav files.
def generate_automated_labels(bird_dir, isolation_parameters, weight_path=None, Normalized_Sample_Rate = 44100):
    # init detector
    # Use Default Microfaune Detector
    if weight_path is None:
        detector = RNNDetector()
    # Use Custom weights for Microfaune Detector
    else:
        detector = RNNDetector(weight_path)

    # init labels dataframe
    annotations = pd.DataFrame()
    # generate local scores for every bird file in chosen directory
    for audio_file in os.listdir(bird_dir):
        # skip directories
        if os.path.isdir(bird_dir+audio_file): continue

        # read file
        SAMPLE_RATE, SIGNAL = audio.load_wav(bird_dir + audio_file)

        # downsample the audio if the sample rate > 44.1 kHz
        # Force everything into the human hearing range.
        # May consider reworking this function so that it upsamples as well
        if SAMPLE_RATE > Normalized_Sample_Rate:
            rate_ratio = Normalized_Sample_Rate / SAMPLE_RATE
            SIGNAL = scipy_signal.resample(
                    SIGNAL, int(len(SIGNAL)*rate_ratio))
            SAMPLE_RATE = Normalized_Sample_Rate
            # resample produces unreadable float32 array so convert back
            #SIGNAL = np.asarray(SIGNAL, dtype=np.int16)

        #print(SIGNAL.shape)
        # convert stereo to mono if needed
        # Might want to compare to just taking the first set of data.
        if len(SIGNAL.shape) == 2:
            SIGNAL = SIGNAL.sum(axis=1) / 2

        # detection
        try:
            microfaune_features = detector.compute_features([SIGNAL])
            global_score,local_scores = detector.predict(microfaune_features)
        except:
            print("Error in detection, skipping", audio_file)
            continue

        # get duration of clip
        duration = len(SIGNAL) / SAMPLE_RATE
        try:
            # Running moment to moment algorithm and appending to a master dataframe.
            new_entry = isolate(local_scores[0], SIGNAL, SAMPLE_RATE, bird_dir, audio_file, isolation_parameters, manual_id = "bird")
            #print(new_entry)
            if annotations.empty == True:
                annotations = new_entry
            else:
                annotations = annotations.append(new_entry)
        except:
            print("Error in isolating bird calls from", audio_file)
            continue
    # Quick fix to indexing
    annotations.reset_index(inplace = True, drop = True)
    return annotations

# Function that takes in a pandas dataframe of annotations and outputs a dataframe of the
# mean, median, mode, quartiles, and standard deviation of the annotation durations.
def annotation_duration_statistics(df):
    # Reading in the Duration column of the passed in dataframe as a Python list
    annotation_lengths = df["DURATION"].to_list()
    # Converting the Python list to a numpy array
    annotation_lengths = np.asarray(annotation_lengths)
    entry = {'COUNT' : np.shape(annotation_lengths)[0],
             'MODE'  : stats.mode(np.round(annotation_lengths,2))[0][0],
             'MEAN'    : np.mean(annotation_lengths),
             'STANDARD DEVIATION' : np.std(annotation_lengths),
             'MIN': np.amin(annotation_lengths),
             'Q1': np.percentile(annotation_lengths,25),
             'MEDIAN'  : np.median(annotation_lengths),
             'Q3' : np.percentile(annotation_lengths,75),
             'MAX'  : np.amax(annotation_lengths)}
    # returning the dictionary as a pandas dataframe
    return pd.DataFrame.from_dict([entry])

# Function that produces graphs with the local score plot and spectrogram of an audio clip. Now integrated with Pandas so you can visualize human and automated annotations.
def local_line_graph(local_scores,clip_name, sample_rate,samples, automated_df=None, human_df=None,log_scale = False, save_fig = False):
    # Calculating the length of the audio clip
    duration = samples.shape[0]/sample_rate
    # Calculating the number of local scores outputted by Microfaune
    num_scores = len(local_scores)

    ## Making sure that the local score of the x-axis are the same across the spectrogram and the local score plot
    step = duration / num_scores
    time_stamps = np.arange(0, duration, step)

    if len(time_stamps) > len(local_scores):
        time_stamps = time_stamps[:-1]

    # general graph features
    fig, axs = plt.subplots(2)
    fig.set_figwidth(22)
    fig.set_figheight(10)
    fig.suptitle("Spectrogram and Local Scores for "+clip_name)
    # score line plot - top plot
    axs[0].plot(time_stamps, local_scores)
    axs[0].set_xlim(0,duration)
    if log_scale:
        axs[0].set_yscale('log')
    else:
        axs[0].set_ylim(0,1)
    axs[0].grid(which='major', linestyle='-')
    # Adding in the optional automated labels from a Pandas DataFrame
    #if automated_df is not None:
    if automated_df.empty == False:
        ndx = 0
        for row in automated_df.index:
            minval = automated_df["OFFSET"][row]
            maxval = automated_df["OFFSET"][row] + automated_df["DURATION"][row]
            axs[0].axvspan(xmin=minval,xmax=maxval,facecolor="yellow",alpha=0.4, label = "_"*ndx + "Automated Labels")
            ndx += 1
    # Adding in the optional human labels from a Pandas DataFrame
    #if human_df is not None:
    if human_df.empty == False:
        ndx = 0
        for row in human_df.index:
            minval = human_df["OFFSET"][row]
            maxval = human_df["OFFSET"][row] + human_df["DURATION"][row]
            axs[0].axvspan(xmin=minval,xmax=maxval,facecolor="red",alpha=0.4, label = "_"*ndx + "Human Labels")
            ndx += 1
    axs[0].legend()

    # spectrogram - bottom plot
    # Will require the input of a pandas dataframe
    Pxx, freqs, bins, im = axs[1].specgram(samples, Fs=sample_rate,
            NFFT=4096, noverlap=2048,
            window=np.hanning(4096), cmap="ocean")
    axs[1].set_xlim(0,duration)
    axs[1].set_ylim(0,22050)
    axs[1].grid(which='major', linestyle='-')

    # save graph
    if save_fig:
        plt.savefig(clip_name + "_Local_Score_Graph.png")

# Wrapper function for the local_line_graph function for ease of use.
# TODO rework function so that instead of generating the automated labels, it takes the automated_df as input
# same as it does with the manual dataframe.
def local_score_visualization(clip_path,weight_path = None, human_df = None,automated_df = False, isolation_parameters = None,log_scale = False, save_fig = False):

    # Loading in the clip with Microfaune's built-in loading function
    SAMPLE_RATE, SIGNAL = audio.load_wav(clip_path)
    # downsample the audio if the sample rate > 44.1 kHz
    # Force everything into the human hearing range.
    if SAMPLE_RATE > 44100:
        rate_ratio = 44100 / SAMPLE_RATE
        SIGNAL = scipy_signal.resample(SIGNAL, int(len(SIGNAL)*rate_ratio))
        SAMPLE_RATE = 44100
        # Converting to Mono if Necessary
    if len(SIGNAL.shape) == 2:
        SIGNAL = SIGNAL.sum(axis=1) / 2

    # Initializing the detector to baseline or with retrained weights
    if weight_path is None:
        detector = RNNDetector()
    else:
        detector = RNNDetector(weight_path)
    try:
        # Computing Mel Spectrogram of the audio clip
        microfaune_features = detector.compute_features([SIGNAL])
        # Running the Mel Spectrogram through the RNN
        global_score,local_score = detector.predict(microfaune_features)
    except:
        print("Error in " + clip_path + " Skipping.")

    # In the case where the user wants to look at automated bird labels
    if human_df is None:
        human_df = pd.DataFrame
    if automated_df == True:
        automated_df = isolate(local_score[0],SIGNAL, SAMPLE_RATE,"Doesn't","Matter",isolation_parameters)
    else:
        automated_df = pd.DataFrame()

    local_line_graph(local_score[0].tolist(),clip_path,SAMPLE_RATE,SIGNAL,automated_df,human_df,log_scale = log_scale, save_fig = save_fig)



def bird_label_scores(automated_df,human_df,plot_fig = False, save_fig = False):

    duration = automated_df["CLIP LENGTH"].to_list()[0]
    SAMPLE_RATE = automated_df["SAMPLE RATE"].to_list()[0]
    # Initializing two arrays that will represent the human labels and automated labels with respect to
    # the audio clip
    #print(SIGNAL.shape)
    human_arr = np.zeros((int(SAMPLE_RATE*duration),))
    bot_arr = np.zeros((int(SAMPLE_RATE*duration),))

    folder_name = automated_df["FOLDER"].to_list()[0]
    clip_name = automated_df["IN FILE"].to_list()[0]
    # Placing 1s wherever the au
    for row in automated_df.index:
        minval = int(round(automated_df["OFFSET"][row]*SAMPLE_RATE,0))
        maxval = int(round((automated_df["OFFSET"][row] + automated_df["DURATION"][row]) *SAMPLE_RATE,0))
        bot_arr[minval:maxval] = 1
    for row in human_df.index:
        minval = int(round(human_df["OFFSET"][row]*SAMPLE_RATE,0))
        maxval = int(round((human_df["OFFSET"][row] + human_df["DURATION"][row])*SAMPLE_RATE,0))
        human_arr[minval:maxval] = 1

    human_arr_flipped = 1 - human_arr
    bot_arr_flipped = 1 - bot_arr

    true_positive_arr = human_arr*bot_arr
    false_negative_arr = human_arr * bot_arr_flipped
    false_positive_arr = human_arr_flipped * bot_arr
    true_negative_arr = human_arr_flipped * bot_arr_flipped
    IoU_arr = human_arr + bot_arr
    IoU_arr[IoU_arr == 2] = 1

    true_positive_count = np.count_nonzero(true_positive_arr == 1)/SAMPLE_RATE
    false_negative_count = np.count_nonzero(false_negative_arr == 1)/SAMPLE_RATE
    false_positive_count = np.count_nonzero(false_positive_arr == 1)/SAMPLE_RATE
    true_negative_count = np.count_nonzero(true_negative_arr == 1)/SAMPLE_RATE
    union_count = np.count_nonzero(IoU_arr == 1)/SAMPLE_RATE

    # Calculating useful values related to tp,fn,fp,tn values

    # Precision = TP/(TP+FP)
    try:
        precision = true_positive_count/(true_positive_count + false_positive_count)


    # Recall = TP/(TP+FP)
        recall = true_positive_count/(true_positive_count + false_negative_count)

    # F1 = 2*(Recall*Precision)/(Recall + Precision)

        f1 = 2*(recall*precision)/(recall + precision)
        IoU = true_positive_count/union_count
    except:
        print("Error calculating statistics, likely due to zero division, setting values to zero")
        f1 = 0
        precision = 0
        recall = 0

    # Creating a Dictionary which will be turned into a Pandas Dataframe
    entry = {'FOLDER'  : folder_name,
             'IN FILE'    : clip_name,
             'TRUE POSITIVE' : true_positive_count,
             'FALSE POSITIVE': false_positive_count,
             'FALSE NEGATIVE'  : false_negative_count,
             'TRUE NEGATIVE'  : true_negative_count,
             'UNION' : union_count,
             'PRECISION' : precision,
             'RECALL' : recall,
             "F1" : f1,
             'Global IoU' : IoU}
    #print(entry)
    # Plotting the three arrays to visualize where
    if plot_fig == True:
        plt.figure(figsize=(22,10))
        plt.subplot(7,1,1)
        plt.plot(human_arr)
        plt.title("Ground Truth for " + clip_name)
        plt.subplot(7,1,2)
        plt.plot(bot_arr)
        plt.title("Automated Label for " + clip_name)

        #Visualizing True Positives for the Automated Labeling
        plt.subplot(7,1,3)
        plt.plot(true_positive_arr)
        plt.title("True Positive for " + clip_name)

        #Visualizing False Negatives for the Automated Labeling
        plt.subplot(7,1,4)
        plt.plot(false_negative_arr)
        plt.title("False Negative for " + clip_name)

        plt.subplot(7,1,5)
        plt.plot(false_positive_arr)
        plt.title("False Positive for " + clip_name)

        plt.subplot(7,1,6)
        plt.plot(true_negative_arr)
        plt.title("True Negative for " + clip_name)

        plt.subplot(7,1,7)
        plt.plot(IoU_arr)
        plt.title("Union for " + clip_name)

        plt.tight_layout()
        if save_fig == True:
            x = clip_name.split(".")
            clip_name = x[0]
            plt.save_fig(clip_name + "_label_plot.png")

    return pd.DataFrame(entry,index=[0])

# Function that will allow users to easily pass in two dataframes, and it will output statistics on them
# Will have to adjust the isolate function so that it adds a sampling rate onto the dataframes.
def automated_labeling_statistics(automated_df,manual_df):
    # Getting a list of clips
    clips = automated_df["IN FILE"].to_list()
    # Removing duplicates
    clips = list(dict.fromkeys(clips))
    # Initializing the returned dataframe
    statistics_df = pd.DataFrame()
    # Looping through each audio clip
    for clip in clips:
        clip_automated_df = automated_df[automated_df["IN FILE"] == clip]
        clip_manual_df = manual_df[manual_df["IN FILE"] == clip]
        #try:
        clip_stats_df = bird_label_scores(clip_automated_df,clip_manual_df)
        if statistics_df.empty:
            statistics_df = clip_stats_df
        else:
            statistics_df = statistics_df.append(clip_stats_df)
        #except:
        #    print("Something went wrong with: "+clip)
        #    continue
        statistics_df.reset_index(inplace = True, drop = True)
    return statistics_df

# Small function that takes in the statistics and outputs their global values
def global_dataset_statistics(statistics_df):
    tp_sum = statistics_df["TRUE POSITIVE"].sum()
    fp_sum = statistics_df["FALSE POSITIVE"].sum()
    fn_sum = statistics_df["FALSE NEGATIVE"].sum()
    tn_sum = statistics_df["TRUE NEGATIVE"].sum()
    union_sum = statistics_df["UNION"].sum()
    precision = tp_sum/(tp_sum + fp_sum)
    recall = tp_sum/(tp_sum + fn_sum)
    f1 = 2*(precision*recall)/(precision+recall)
    IoU = tp_sum/union_sum
    entry = {'PRECISION'  : round(precision,6),
             'RECALL'    : round(recall,6),
             'F1' : round(f1,6),
             'Global IoU' : round(IoU,6)}
    return pd.DataFrame.from_dict([entry])

# TODO rework this function to implement some linear algebra, right now the nested for loop won't handle larger loads well
# To make a global matrix, find the clip with the most amount of automated labels and set that to the number of columns
def clip_IoU(automated_df,manual_df):
    automated_df.reset_index(inplace = True, drop = True)
    manual_df.reset_index(inplace = True, drop = True)
    # Determining the number of rows in the output numpy array
    manual_row_count = manual_df.shape[0]
    # Determining the number of columns in the output numpy array
    automated_row_count = automated_df.shape[0]

    # Determining the length of the input clip
    duration = automated_df["CLIP LENGTH"].to_list()[0]
    # Determining the sample rate of the input clip
    SAMPLE_RATE = automated_df["SAMPLE RATE"].to_list()[0]

    # Initializing the output array that will contain the clip-by-clip Intersection over Union percentages.
    IoU_Matrix = np.zeros((manual_row_count,automated_row_count))
    #print(IoU_Matrix.shape)

    # Initializing arrays that will represent each of the human and automated labels
    bot_arr = np.zeros((int(duration * SAMPLE_RATE)))
    human_arr = np.zeros((int(duration * SAMPLE_RATE)))

    # Looping through each human label
    for row in manual_df.index:
        #print(row)
        # Determining the beginning of a human label
        minval = int(round(manual_df["OFFSET"][row]*SAMPLE_RATE,0))
        # Determining the end of a human label
        maxval = int(round((manual_df["OFFSET"][row] + manual_df["DURATION"][row]) *SAMPLE_RATE,0))
        # Placing the label relative to the clip
        human_arr[minval:maxval] = 1
        # Looping through each automated label
        for column in automated_df.index:
            # Determining the beginning of an automated label
            minval = int(round(automated_df["OFFSET"][column]*SAMPLE_RATE,0))
            # Determining the ending of an automated label
            maxval = int(round((automated_df["OFFSET"][column] + automated_df["DURATION"][column]) *SAMPLE_RATE,0))
            # Placing the label relative to the clip
            bot_arr[minval:maxval] = 1
            # Determining the overlap between the human label and the automated label
            intersection = human_arr * bot_arr
            # Determining the union between the human label and the automated label
            union = human_arr + bot_arr
            union[union == 2] = 1
            # Determining how much of the human label and the automated label overlap with respect to time
            intersection_count = np.count_nonzero(intersection == 1)/SAMPLE_RATE
            # Determining the span of the human label and the automated label with respect to time.
            union_count = np.count_nonzero(union == 1)/SAMPLE_RATE
            # Placing the Intersection over Union Percentage into it's respective position in the array.
            IoU_Matrix[row,column] = round(intersection_count/union_count,4)
            # Resetting the automated label to zero
            bot_arr[bot_arr == 1] = 0
        # Resetting the human label to zero
        human_arr[human_arr == 1] = 0

    return IoU_Matrix
# Function that takes in the IoU Matrix from the clip_IoU function and ouputs the number of true positives and false positives
# It also calculates the precision.
def matrix_IoU_Scores(IoU_Matrix,manual_df,threshold):

    audio_dir = manual_df["FOLDER"][0]
    filename = manual_df["IN FILE"][0]

    # Determining which automated label has the highest IoU across each human label
    automated_label_best_fits = np.max(IoU_Matrix,axis=1)
    #human_label_count = automated_label_best_fits.shape[0]
    # Calculating the number of true positives based off of the passed in thresholds.
    tp_count = automated_label_best_fits[automated_label_best_fits >= threshold].shape[0]
    # Calculating the number of false negatives from the number of human labels and true positives
    fn_count = automated_label_best_fits[automated_label_best_fits < threshold].shape[0]

    # Calculating the false positives
    max_val_per_column = np.max(IoU_Matrix,axis=0)
    fp_count = max_val_per_column[max_val_per_column < threshold].shape[0]

    # Calculating the necessary statistics
    try:
        recall = round(tp_count/(tp_count+fn_count),4)
        precision = round(tp_count/(tp_count+fp_count),4)
        f1 = round(2*(recall*precision)/(recall+precision),4)
    except:
        print("Division by zero setting precision, recall, and f1 to zero")
        recall = 0
        precision = 0
        f1 = 0

    entry = {'FOLDER'  : audio_dir,
             'IN FILE'    : filename,
             'TRUE POSITIVE' : tp_count,
             'FALSE NEGATIVE' : fn_count,
             'FALSE POSITIVE': fp_count,
             'PRECISION'  : precision,
             'RECALL' : recall,
             'F1' : f1}

    return pd.DataFrame.from_dict([entry])

# Function that can help us determine whether or not a call was detected.
def clip_catch(automated_df,manual_df):
    # resetting the indices to make this function work
    automated_df.reset_index(inplace = True, drop = True)
    manual_df.reset_index(inplace = True, drop = True)
    # figuring out how many automated labels and human labels exist
    manual_row_count = manual_df.shape[0]
    automated_row_count = automated_df.shape[0]
    # finding the length of the clip as well as the sampling frequency.
    duration = automated_df["CLIP LENGTH"].to_list()[0]
    SAMPLE_RATE = automated_df["SAMPLE RATE"].to_list()[0]
    # initializing the output array, as well as the two arrays used to calculate catch scores
    catch_matrix = np.zeros(manual_row_count)
    bot_arr = np.zeros((int(duration * SAMPLE_RATE)))
    human_arr = np.zeros((int(duration * SAMPLE_RATE)))

    # Determining the automated labelled regions with respect to samples
    # Looping through each human label
    for row in automated_df.index:
        # converting each label into a "pulse" on an array that represents the labels as 0's and 1's on bot array.
        minval = int(round(automated_df["OFFSET"][row]*SAMPLE_RATE,0))
        maxval = int(round((automated_df["OFFSET"][row] + automated_df["DURATION"][row]) *SAMPLE_RATE,0))
        bot_arr[minval:maxval] = 1

    # Looping through each human label and computing catch = (#intersections)/(#samples in label)
    for row in manual_df.index:
        # Determining the beginning of a human label
        minval = int(round(manual_df["OFFSET"][row]*SAMPLE_RATE,0))
        # Determining the end of a human label
        maxval = int(round((manual_df["OFFSET"][row] + manual_df["DURATION"][row]) *SAMPLE_RATE,0))
        # Placing the label relative to the clip
        human_arr[minval:maxval] = 1
        # Determining the length of a label with respect to samples
        samples_in_label = maxval - minval
        # Finding where the human label and all of the annotated labels overlap
        intersection = human_arr * bot_arr
        # Determining how many samples overlap.
        intersection_count = np.count_nonzero(intersection == 1)
        # Intersection/length of label
        catch_matrix[row] = round(intersection_count/samples_in_label,4)
        # resetting the human label
        human_arr[human_arr == 1] = 0

    return catch_matrix



# Function that takes in two Pandas dataframes that represent human labels and automated labels.
# It then runs the clip_IoU function across each clip and appends the best fit IoU score to each labels
# on the manual dataframe as its output.
def dataset_IoU(automated_df,manual_df):
    # Getting a list of clips
    clips = automated_df["IN FILE"].to_list()
    # Removing duplicates
    clips = list(dict.fromkeys(clips))
    # Initializing the ouput dataframe
    manual_df_with_IoU = pd.DataFrame()
    for clip in clips:
        print(clip)
        # Isolating a clip from the human and automated dataframes
        clip_automated_df = automated_df[automated_df["IN FILE"] == clip]
        clip_manual_df = manual_df[manual_df["IN FILE"] == clip]
        # Calculating the IoU scores of each human label.
        IoU_Matrix = clip_IoU(clip_automated_df,clip_manual_df)
        # Finding the best automated IoU score with respect to each label
        automated_label_best_fits = np.max(IoU_Matrix,axis=1)
        clip_manual_df["IoU"] = automated_label_best_fits
        # Appending on the best fit IoU score to each human label
        if manual_df_with_IoU.empty == True:
            manual_df_with_IoU = clip_manual_df
        else:
            manual_df_with_IoU = manual_df_with_IoU.append(clip_manual_df)
    # Adjusting the indices.
    manual_df_with_IoU.reset_index(inplace = True, drop = True)
    return manual_df_with_IoU


def dataset_IoU_Statistics(automated_df,manual_df,threshold = 0.5):
    # isolating the names of the clips that have been labelled into an array.
    clips = automated_df["IN FILE"].to_list()
    clips = list(dict.fromkeys(clips))
    # initializing the output Pandas dataframe
    IoU_Statistics = pd.DataFrame()
    # Looping through all of the clips
    for clip in clips:
        print(clip)
        # isolating the clip into its own dataframe with respect to both the passed in human labels and automated labels.
        clip_automated_df = automated_df[automated_df["IN FILE"] == clip]
        clip_manual_df = manual_df[manual_df["IN FILE"] == clip]
        # Computing the IoU Matrix across a specific clip
        IoU_Matrix = clip_IoU(clip_automated_df,clip_manual_df)
        # Calculating the best fit IoU to each label for the clip
        clip_stats_df = matrix_IoU_Scores(IoU_Matrix,clip_manual_df,threshold)
        # adding onto the output array.
        if IoU_Statistics.empty == True:
            IoU_Statistics = clip_stats_df
        else:
            IoU_Statistics = IoU_Statistics.append(clip_stats_df)
    IoU_Statistics.reset_index(inplace = True, drop = True)
    return IoU_Statistics
# Function that takes the output of dataset_IoU_Statistics and computes a global precision score.
def global_IoU_Statistics(statistics_df):
    # taking the sum of the number of true positives and false positives.
    tp_sum = statistics_df["TRUE POSITIVE"].sum()
    fn_sum = statistics_df["FALSE NEGATIVE"].sum()
    fp_sum = statistics_df["FALSE POSITIVE"].sum()
    # calculating the precision, recall, and f1
    try:
        precision = tp_sum/(tp_sum+fp_sum)
        recall = tp_sum/(tp_sum+fn_sum)
        f1 = 2*(precision*recall)/(precision+recall)
    except:
        print("Error in calculating Precision, Recall, and F1. Likely due to zero division, setting values to zero")
        precision = 0
        recall = 0
        f1 = 0
    # building a dictionary of the above calculations
    entry = {'TRUE POSITIVE' : tp_sum,
        'FALSE NEGATIVE' : fn_sum,
        'FALSE POSITIVE' : fp_sum,
        'PRECISION'  : round(precision,4),
        'RECALL' : round(recall,4),
        'F1' : round(f1,4)}
    # returning the dictionary as a pandas dataframe
    return pd.DataFrame.from_dict([entry])

def dataset_Catch(automated_df,manual_df):
    # Getting a list of clips
    clips = automated_df["IN FILE"].to_list()
    # Removing duplicates
    clips = list(dict.fromkeys(clips))
    # Initializing the ouput dataframe
    manual_df_with_Catch = pd.DataFrame()
    # Looping through all of the audio clips that have been labelled.
    for clip in clips:
        print(clip)
        # Isolating the clips from both the automated and human dataframes
        clip_automated_df = automated_df[automated_df["IN FILE"] == clip]
        clip_manual_df = manual_df[manual_df["IN FILE"] == clip]
        # Calling the function that calculates the catch over a specific clip
        Catch_Array = clip_catch(clip_automated_df,clip_manual_df)
        # Appending the catch values per label onto the manual dataframe
        clip_manual_df["Catch"] = Catch_Array
        if manual_df_with_Catch.empty == True:
            manual_df_with_Catch = clip_manual_df
        else:
            manual_df_with_Catch = manual_df_with_Catch.append(clip_manual_df)
    # Resetting the indices
    manual_df_with_Catch.reset_index(inplace = True, drop = True)
    return manual_df_with_Catch
