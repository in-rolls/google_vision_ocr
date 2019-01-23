#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
google_vision_ocr.py: goes through a directory of png files and outputs text
and json files in an output directory with the same file name as input file.
So, for instance, abc_1_15.png produces abc_1_15.txt and abc_1_15.json.

Modified from: python-docs-samples/vision/cloud-client/document_text/doctext.py
"""

# [START vision_document_text_tutorial]
# [START vision_document_text_tutorial_imports]
import os
import argparse
from enum import Enum
import io
import time
from glob import glob

from google.cloud import vision
from google.cloud.vision import types
from PIL import Image, ImageDraw
# [END vision_document_text_tutorial_imports]


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


def detect_document_text(image_file, textfile, jsonfile):
    """Returns document text given an image."""
    client = vision.ImageAnnotatorClient()

    with io.open(image_file, 'rb') as image_file:
        content = image_file.read()

    image = types.Image(content=content)
    image_context = types.ImageContext(language_hints=['en'])

    response = client.document_text_detection(image=image, timeout=300, image_context=image_context)
    document = response.full_text_annotation

    if textfile is not 0:
        with io.open(textfile, 'wb') as f:
            f.write(document.text.encode('utf-8'))

    if jsonfile is not 0:
        with io.open(jsonfile, 'wb') as f:
            f.write(str(document))

    return document


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


def render_doc_text(filein, fileout, textfile, jsonfile):
    doc = detect_document_text(filein, textfile, jsonfile)
    image = Image.open(filein)
    bounds = get_document_bounds(doc, FeatureType.BLOCK)
    draw_boxes(image, bounds, 'blue')
    bounds = get_document_bounds(doc, FeatureType.PARA)
    draw_boxes(image, bounds, 'red')
    bounds = get_document_bounds(doc, FeatureType.WORD)
    draw_boxes(image, bounds, 'green')

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
    print("Confidence: %0.4f" % (sum / n))


if __name__ == "__main__":
    title = 'OCR PNG files in the directory using Google Vision API'
    parser = argparse.ArgumentParser(description=title)
    parser.add_argument('directory', default=None,
                        help='Directory contains PNG files')
    parser.add_argument('--overwritten',
                        help='Overwrite if output file exists',
                        action='store_true')
    parser.add_argument('-o', '--output', default='output',
                        help='Directory for output files')

    args = parser.parse_args()

    print(args)

    if not os.path.exists(args.output):
        os.makedirs(args.output)

    for filein in glob(os.path.join(args.directory, '*.png')):
        print('Processing...{:s}'.format(filein))
        base_fn = os.path.basename(filein)
        fn = os.path.splitext(base_fn)[0]
        fileout = os.path.join(args.output, fn + '.png')
        if os.path.exists(fileout) and not args.overwritten:
            print("- Output exists, skip...")
            continue
        textfile = os.path.join(args.output, fn + '.txt')
        jsonfile = os.path.join(args.output, fn + '.json')
        start = time.time()
        render_doc_text(filein, fileout, textfile, jsonfile)
        duration = time.time() - start
        print("- Duration: %0.1f" % (duration))
