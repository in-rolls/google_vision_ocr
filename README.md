## Using Google Vision API to Get Text From (Unreadable) Electoral Rolls

Use the Google Vision API to get the text from electoral rolls that are encoded as images or encoded incorrectly.

The key innovation in the script is a money saving one: we combine multiple pages of electoral rolls into one image so that we can hit the max. pixels (size) per request. Here's the broad workflow we automate: 1) split electoral rolls into multi-page chunks, 2) name the chunks in a way that makes the ancestry clear so that we can combine the results easily, 3) combine the multi-page chunk into an image and pass it to Google, 4) get the results (text, JSON, PNG with bounding boxes) with appropriate names.  

---------------

### Included:

1. [Why Choose the Google Vision API? Price and Convenience](#why-choose-google-vision-api)
2. [Issues with Using the Google Vision API](#issues)
3. [Scripts](#scripts)
4. [Installing the Scripts](#install)
5. [Using the Scripts](#usage)
6. [Application](#application)

----------------


### Why Choose Google Vision API?

One reason for using the Google Vision API is simply that [Indian Electoral Roll PDFs](https://github.com/in-rolls/electoral_rolls) are on Google Cloud Coldline Storage. But besides convenience, [Google Vision API](https://cloud.google.com/vision/) also offers value. Google Vision API OCR can be more than 300x cheaper than [Abbyy Cloud OCR](https://www.ocrsdk.com/plans-and-pricing/). (The precise number depends on how many pages you need to process.) For instance, we processed 15,000 pages. On Google, we were able to combine 15,000 pages into ~ 1,000 requests. Assuming that we had exhausted the free tier, the price for 1,000 requests is $1.5. Had we tried to get text from 15,000 pages from AbbyyFine, we would have had to pay $450---$300 for the 10,000 tier + .03 per page for the remaining 5,000 pages.

### Issues

Funnily, Google Vision API is capable of giving  **worse outputs** at a higher resolution. At the minimum, increasing resolution introduces errors which weren't there when you fed in at a lower resolution.

Besides that, the other concern is that the final text file that you get from the Google Vision API is virtually worthless because the API cannot detect the layout very well. To detect the layout, you will have to build an engineering solution on top of the JSON, which preserves coordinates of each identified letter.

### Scripts

1. [Split Electoral Rolls](split_elex_rolls.py): Takes a directory of electoral roll pdfs and depending on the resolution (passed as an option), splits each electoral roll into appropriate size pngs preserving the filename and outputs the pngs to `png/`. For instance, for an electoral roll file named `abc.pdf` with a resolution of 300 dpi, we generate `abc_1_15.png`, `abc_16_30.png`, etc. till all the pages in `abc` are exhausted. 
    
    * **Note:** Given each file gives data of a polling station, we do not combine pages from multiple electoral rolls.

2. [Google Vision API: OCR Request](google_vision_ocr.py): Uses the [OCR method](https://cloud.google.com/vision/docs/ocr) from the API. It goes through a directory of png files and outputs text and JSON files in an output directory with the same file name as the input file. So, for instance, `abc_1_15.png` produces `abc_1_15.txt` and `abc_1_15.json`.
    
    * **API Method Limit:** If you are passing a png to the [OCR method](https://cloud.google.com/vision/docs/ocr), you can submit a maximum of 89,478,485 pixels per request.

3. [Google Vision API: Async PDF/TIFF Document Text Detection](google_vision_ocr_gcs.py): Same as #2 but optimized to process a large number of png files. The Google Cloud Storage bucket will be used to share the input and output files between the OCR worker process and Google Vision API. The [following diagram](gcs_workflow.md) shows the workflow of the OCR worker process. The number of OCR worker process can be specified by the `-p` option.

    * **API Method Limit:** For [async pdf API request](https://cloud.google.com/vision/docs/pdf), the limit is 2,000 pages or 20MB. The file size/number of pages puts an informal restriction on the resolution.


### Install

```
git clone https://github.com/in-rolls/google_vision_ocr.git
cd google_vision_ocr
pip install -r requirements.txt
```

### Usage

```
usage: google_vision_ocr_gcs.py [-h] [-b BUCKET_NAME] [-c CREDENTIALS]
                                [--overwritten] [-o OUTPUT] [-p PROCESSES]
                                [--log-level [LOG_LEVEL]]
                                directory

OCR PNG files in the directory using Google Vision API

positional arguments:
  directory             Directory contains PNG files

optional arguments:
  -h, --help            show this help message and exit
  -b BUCKET_NAME, --bucket-name BUCKET_NAME
                        Working bucket name on Google Cloud Storage
  -c CREDENTIALS, --credentials CREDENTIALS
                        Google Applicaiton Credentials file
  --overwritten         Overwrite if output file exists
  -o OUTPUT, --output OUTPUT
                        Directory for output files
  -p PROCESSES, --processes PROCESSES
                        Number of worker process to run (Default: 10)
  --log-level [LOG_LEVEL]
                        Set the logging output level. ['CRITICAL', 'ERROR',
                        'WARNING', 'INFO', 'DEBUG']
```

### Application

To illustrate how to use the script, we use it to process 15,000 Kerala English PDF Electoral Rolls. 

We processed the electoral rolls using the [async pdf API request](https://cloud.google.com/vision/docs/pdf). We first split the electoral files using [split_elex_rolls.py](split_elex_rolls.py) into 15 page chunks. (We chose 15 pages after checking out errors at different resolutions. At 300 dpi, it turns out to be about 15 pages of electoral rolls. And returns on increasing resolution beyond 300 dpi are minimal.) We then called [google_vision_ocr_gcs.py](google_vision_ocr_gcs.py), which implements the [following workflow](gcs_workflow.md). 

#### Output, Errors, Stats, and Utility Script

1. **Data:** The output (text, JSON, png with bounding boxes) from 15,000 pages of Kerala English Electoral Rolls is available at: [Harvard Dataverse](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/MQPPNC).  (**Note:** Given the data include personal details of electors, we are only releasing the data for researchers.)

2. **Log File and Stats:** Check out the [log file](sample_out/mplog.log) for details about failed requests, the [script](sample_out/google_vision_ocr_log2stat.ipynb) that gets statistics on the OCR confidence, and the resulting [stats (csv)](sample_out/google_vision_ocr_stat.csv). 

3. **Error Analysis:** When we analyzed the log file, we found two kinds of errors `WARNING  image file is truncated (retry=0)`, and `Backend deadline exceeded. Error processing features.` The former was produced because we had prematurely truncated split_elex_rolls script. The source of the latter error is not clear, except that Google will charge for these failed requests. (We had about a 100 of such requests.)

4. **Utility Script for Uploading Data to Dataverse:** To upload the big tar gzipped file to Dataverse, we chunked the file into multiple files so that each had a size equal to or less than the max. size allowed on Dataverse using [split](https://www.tecmint.com/split-large-tar-into-multiple-files-of-certain-size/) and then uploaded the chunks using this [script](https://gist.github.com/suriyan/ffe979445a8f419c10bc939419062fc9).
