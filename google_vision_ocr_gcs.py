#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
google_vision_ocr_gcs.py: goes through a directory of png files and outputs text
and json files in an output directory with the same file name as input file.
So, for instance, abc_1_15.png produces abc_1_15.txt and abc_1_15.json.

"""

import os
import argparse
import io
import time
import sys
import re
import tempfile
import json
import logging

from enum import Enum
from glob import glob
from multiprocessing import Pool, Queue
from functools import partial

import img2pdf

from google.cloud import storage
from google.cloud import vision
from google.cloud.vision import types
from google.protobuf import json_format

from PIL import Image, ImageDraw

from logutils.queue import QueueHandler, QueueListener


MAX_RETRY = 10
GOOGLE_OPERATION_TIMEOUT = 600
LOG_FILE = 'mplog.log'


def worker_init(q, level=logging.INFO):
    # all records from worker processes go to qh and then into q
    qh = QueueHandler(q)
    logger = logging.getLogger()
    logger.setLevel(level)
    logger.addHandler(qh)


def logger_init(level=logging.INFO):
    q = Queue()

    # this is the handler for all log records
    handler = logging.StreamHandler()
    f = logging.Formatter('%(asctime)s %(processName)-10s %(name)s %(levelname)-8s %(message)s')
    handler.setFormatter(f)

    file_handler = logging.FileHandler(LOG_FILE, 'a')
    f = logging.Formatter('%(asctime)s %(processName)-10s %(name)s %(levelname)-8s %(message)s')
    file_handler.setFormatter(f)

    # ql gets records from the queue and sends them to the handler
    ql = QueueListener(q, handler, file_handler)
    ql.start()

    logger = logging.getLogger()
    logger.setLevel(level)
    # add the handler to the logger so records from this process are handled
    logger.addHandler(handler)
    logger.addHandler(file_handler)

    return ql, q


class FeatureType(Enum):
    PAGE = 1
    BLOCK = 2
    PARA = 3
    WORD = 4
    SYMBOL = 5


def draw_boxes(image, bounds, color):
    """Draw a border around the image using the hints in the vector list."""
    draw = ImageDraw.Draw(image)

    for bound in bounds:
        draw.polygon([
            bound.vertices[0].x, bound.vertices[0].y,
            bound.vertices[1].x, bound.vertices[1].y,
            bound.vertices[2].x, bound.vertices[2].y,
            bound.vertices[3].x, bound.vertices[3].y], None, color)
    return image


def draw_norm_boxes(image, bounds, color):
    """Draw a border around the image using the hints in the vector list."""
    draw = ImageDraw.Draw(image)
    w, h = image.size

    for bound in bounds:
        draw.polygon([
            bound.normalized_vertices[0].x * w, bound.normalized_vertices[0].y * h,
            bound.normalized_vertices[1].x * w, bound.normalized_vertices[1].y * h,
            bound.normalized_vertices[2].x * w, bound.normalized_vertices[2].y * h,
            bound.normalized_vertices[3].x * w, bound.normalized_vertices[3].y * h], None, color)
    return image


def download_blob(bucket_name, src_blob_name, dst_file_name):
    """Downloads a blob from the bucket."""
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(src_blob_name)
    blob.download_to_filename(dst_file_name)


def upload_blob(bucket_name, source_file_name, destination_blob_name):
    """Uploads a file to the bucket."""
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)

    blob.upload_from_filename(source_file_name)


def delete_blob(bucket_name, blob_name):
    """Deletes a blob from the bucket."""
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(blob_name)

    blob.delete()


def delete_bucket(bucket_name):
    """Deletes a bucket. The bucket must be empty."""
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(bucket_name)
    bucket.delete()


def create_bucket(bucket_name):
    """Creates a new bucket."""
    storage_client = storage.Client()
    bucket = storage_client.create_bucket(bucket_name)


def get_bucket_name():
    temp_name = next(tempfile._get_candidate_names())
    return temp_name


def async_detect_document_text(bucket_name, image_file, textfile, jsonfile):
    # Supported mime_types are: 'application/pdf' and 'image/tiff'
    mime_type = 'application/pdf'

    tmp_dir = tempfile._get_default_tempdir()

    png_fn = os.path.basename(image_file)
    fn = os.path.splitext(png_fn)[0]
    pdf_fn = fn + '.pdf'
    prefix_fn = fn + '-'
    pdf_path = os.path.join(tmp_dir, pdf_fn)

    gcs_src_uri = 'gs://{}/{}'.format(bucket_name, pdf_fn)
    gcs_dst_uri = 'gs://{}/{}'.format(bucket_name, prefix_fn)

    logging.info('Converting... {!s}'.format(png_fn))
    with open(pdf_path,"wb") as f:
        f.write(img2pdf.convert([image_file]))

    logging.info('Uploading... {!s}'.format(pdf_fn))
    upload_blob(bucket_name, pdf_path, pdf_fn)

    os.unlink(pdf_path)

    # How many pages should be grouped into each json output file.
    # With a file of 1 pages
    batch_size = 1

    client = vision.ImageAnnotatorClient()

    feature = types.Feature(
        type=vision.enums.Feature.Type.DOCUMENT_TEXT_DETECTION)

    gcs_src = types.GcsSource(uri=gcs_src_uri)
    input_config = types.InputConfig(gcs_source=gcs_src,
                                    mime_type=mime_type)

    gcs_dst = types.GcsDestination(uri=gcs_dst_uri)
    output_config = types.OutputConfig(gcs_destination=gcs_dst,
                                    batch_size=batch_size)

    image_context = types.ImageContext(language_hints=['en'])

    async_request = types.AsyncAnnotateFileRequest(
        features=[feature], input_config=input_config,
        output_config=output_config, image_context=image_context)

    operation = client.async_batch_annotate_files(
        requests=[async_request])

    logging.info('Waiting... {!s}'.format(gcs_src_uri))
    result = operation.result(timeout=GOOGLE_OPERATION_TIMEOUT)
    logging.debug('{!s}'.format(result))

    delete_blob(bucket_name, pdf_fn)

    # Once the request has completed and the output has been
    # written to GCS, we can list all the output files.
    storage_client = storage.Client()

    match = re.match(r'gs://([^/]+)/(.+)', gcs_dst_uri)
    bucket_name = match.group(1)
    prefix = match.group(2)

    bucket = storage_client.get_bucket(bucket_name=bucket_name)

    # List objects with the given prefix.
    blob_list = list(bucket.list_blobs(prefix=prefix))

    # Process the first output file from GCS.
    # Since we specified batch_size=1, the first response contains
    # the first page of the input file.
    output = blob_list[0]

    logging.info('Downloading... {!s}'.format(output.name))

    json_string = output.download_as_string()

    logging.debug('JSON len={:d}'.format(len(json_string)))

    response = json_format.Parse(
        json_string, types.AnnotateFileResponse())

    # The actual response for the first page of the input file.
    document = response.responses[0].full_text_annotation

    if textfile is not 0:
        logging.info('Saving... {!s}'.format(textfile))
        with io.open(textfile, 'wb') as f:
            f.write(document.text.encode('utf-8'))

    if jsonfile is not 0:
        logging.info('Saving... {!s}'.format(jsonfile))
        with io.open(jsonfile, 'wb') as f:
            f.write(str(document))

    output.delete()

    return document


def denorm_bbox(page, bbox):
    bb  = types.BoundingPoly()
    vertices = []
    for nv in bbox.normalized_vertices:
        v = types.Vertex()
        v.x = int(nv.x * page.width)
        v.y = int(nv.y * page.height)
        vertices.append(v)
    bb.vertices.extend(vertices)
    return bb


def get_document_bounds(document, feature):
    # [START vision_document_text_tutorial_detect_bounds]
    bounds = []

    # Collect specified feature bounds by enumerating all document features
    for page in document.pages:
        for block in page.blocks:
            for paragraph in block.paragraphs:
                for word in paragraph.words:
                    for symbol in word.symbols:
                        if (feature == FeatureType.SYMBOL):
                            bounds.append(symbol.bounding_box)

                    if (feature == FeatureType.WORD):
                        bounds.append(word.bounding_box)

                if (feature == FeatureType.PARA):
                    bounds.append(paragraph.bounding_box)

            if (feature == FeatureType.BLOCK):
                bounds.append(block.bounding_box)

        if (feature == FeatureType.PAGE):
            bounds.append(block.bounding_box)

    # The list `bounds` contains the coordinates of the bounding boxes.
    # [END vision_document_text_tutorial_detect_bounds]
    return bounds


def render_doc_text(bucket_name, filein, fileout, textfile, jsonfile):
    retry = 0
    while True:
        try:
            doc = async_detect_document_text(bucket_name, filein, textfile, jsonfile)
            image = Image.open(filein)
            bounds = get_document_bounds(doc, FeatureType.BLOCK)
            draw_norm_boxes(image, bounds, 'blue')
            bounds = get_document_bounds(doc, FeatureType.PARA)
            draw_norm_boxes(image, bounds, 'red')
            bounds = get_document_bounds(doc, FeatureType.WORD)
            draw_norm_boxes(image, bounds, 'green')

            if fileout is not 0:
                image.save(fileout)
            else:
                image.show()

            n = 0
            sum = 0
            for p in doc.pages:
                for b in p.blocks:
                    sum += b.confidence
                    n += 1.0
            conf = (sum / n)
            break
        except Exception as e:
            logging.warn('{!s} (retry={:d})'.format(e, retry))
            retry += 1
            if retry > MAX_RETRY:
                logging.error('Max retry, stoppped!!!')
                conf = 0
                break
    return conf


def ocr_worker(args, filein):
    logging.info('Processing...{:s}'.format(filein))
    base_fn = os.path.basename(filein)
    fn = os.path.splitext(base_fn)[0]
    fileout = os.path.join(args.output, fn + '.png')
    if os.path.exists(fileout) and not args.overwritten:
        logging.info(" - Output exists, skip...")
        return None
    textfile = os.path.join(args.output, fn + '.txt')
    jsonfile = os.path.join(args.output, fn + '.json')
    start = time.time()
    conf = 0
    conf = render_doc_text(args.bucket_name, filein, fileout, textfile, jsonfile)
    duration = time.time() - start
    logging.info(" - Duration: %0.1f" % (duration))
    logging.info(" - Confidence: %0.4f" % (conf))
    return (fileout, duration, conf)


_LOG_LEVEL_STRINGS = ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']

def _log_level_string_to_int(log_level_string):
    if not log_level_string in _LOG_LEVEL_STRINGS:
        message = 'invalid choice: {0} (choose from {1})'.format(log_level_string, _LOG_LEVEL_STRINGS)
        raise argparse.ArgumentTypeError(message)

    log_level_int = getattr(logging, log_level_string, logging.INFO)
    # check the logging log_level_choices have not changed from our expected values
    assert isinstance(log_level_int, int)

    return log_level_int


if __name__ == "__main__":

    title = 'OCR PNG files in the directory using Google Vision API'
    parser = argparse.ArgumentParser(description=title)
    parser.add_argument('directory', default=None,
                        help='Directory contains PNG files')
    parser.add_argument('-b', '--bucket-name', default=None,
                        help='Working bucket name on Google Cloud Storage')
    parser.add_argument('-c', '--credentials', default=None,
                        help='Google Applicaiton Credentials file')
    parser.add_argument('--overwritten',
                        help='Overwrite if output file exists',
                        action='store_true')
    parser.add_argument('-o', '--output', default='output',
                        help='Directory for output files')
    parser.add_argument('-p', '--processes', type=int, default=10,
                        help='Number of worker process to run (Default: 10)')
    parser.add_argument('--log-level', default='INFO', nargs='?',
                        type=_log_level_string_to_int,
                        help='Set the logging output level. {0}'
                            .format(_LOG_LEVEL_STRINGS))
    args = parser.parse_args()

    if 'GOOGLE_APPLICATION_CREDENTIALS' not in os.environ:
        if args.credentials is None:
            print("ERROR: Please make sure have a Google credentials file.\n"
                  "See https://cloud.google.com/docs/authentication/getting-started")
            sys.exit(-1)
        else:
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = args.credentials

    if not os.path.exists(args.output):
        os.makedirs(args.output)

    input_files = sorted(glob(os.path.join(args.directory, '*.png')))

    if args.bucket_name is None:
        while True:
            try:
                args.bucket_name = get_bucket_name()
                create_bucket(args.bucket_name)
                args.auto_bucket = True
                break
            except Exception as e:
                print(e)
    else:
        args.auto_bucket = False

    lq_listener, lq = logger_init(args.log_level)

    logging.info(title)
    logging.info("Args: {!s}".format(args))
    logging.info("Working bucket name on the GCS: {!s}".format(args.bucket_name))

    try:
        pool = Pool(args.nthreads, worker_init, [lq, args.log_level])

        results = pool.map(partial(ocr_worker, args), input_files)

        pool.close()
        pool.join()

        for i, r in enumerate(results):
            logging.info('{!s}: {!s}'.format(input_files[i], r))
    except Exception as e:
        logging.error(e)
    finally:
        if args.auto_bucket:
            delete_bucket(args.bucket_name)

    lq_listener.stop()
