#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
split_elex_rolls.py: Takes a directory of electoral roll pdfs and depending
on the resolution (passed as an option), for each electoral roll, splits the
electoral roll into appropriate size pngs preserving the filename and outputs
it to pngs/. For instance, for electoral roll file name abc.pdf with a
resolution of 300 dpi, we generate abc_1_15.png, abc_16_30.png, etc. till all
the pages in abc are exhausted. Given each file gives data of a polling
station, we do not merge pages from across electoral rolls.
"""
import os
import argparse
from glob import glob
import fitz
from PIL import Image
from io import StringIO, BytesIO


def pdf_to_tile_png(args, pdf_fn):
    til = None
    batch = args.batch
    dpi = args.resolution

    print("Processing....{:s}".format(pdf_fn))
    doc = fitz.open(pdf_fn)
    page_count = doc.pageCount
    from_pno = 1
    for i, page in enumerate(doc):
        pno = i + 1
        print("- Page: {:d}/{:d}".format(pno, page_count))
        zoom = dpi / 96.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.getPixmap(matrix=mat, alpha=False)
        data = pix.getPNGData()
        im = Image.open(BytesIO(data))
        if til is None:
            npage = page_count - pno + 1
            ntile = batch if npage > batch else npage
            til = Image.new("RGB", (pix.w, pix.h * ntile))
        til.paste(im, (0, pix.h * (i % batch)))
        im.close()
        if (pno % batch == 0) or (pno == page_count):
            base_fn = os.path.basename(pdf_fn)
            fn = os.path.splitext(base_fn)[0]
            png_fn = "{:s}-{:d}-{:d}-{:d}.png".format(fn, dpi, from_pno, pno)
            png_fn = os.path.join(args.output, png_fn)
            print("Output: {:s}".format(png_fn))
            til.save(png_fn)
            til.close()
            til = None
            from_pno = pno + 1


if __name__ == "__main__":
    title = 'Split PDF files and create tile of pages as PNG output files'
    parser = argparse.ArgumentParser(description=title)
    parser.add_argument('directory', default=None,
                        help='Directory contains PDF files')
    parser.add_argument('-r', '--resolution', type=int, default=300,
                        choices=[100, 150, 200, 300, 400, 500, 600],
                        help='Output resolution of PNG file')
    parser.add_argument('-b', '--batch', type=int, default=10,
                        help='Number of page to be tiled in a PNG file')
    parser.add_argument('-o', '--output', default='pngs',
                        help='Directory of PNG output files')

    args = parser.parse_args()

    print(args)

    if not os.path.exists(args.output):
        os.makedirs(args.output)

    for fn in sorted(glob(os.path.join(args.directory, '*.pdf'))):
        pdf_to_tile_png(args, fn)
