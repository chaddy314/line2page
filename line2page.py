import glob
#  import getpass
import os
import sys
import multiprocessing
from multiprocessing import Semaphore
import argparse
import time
import ntpath
from datetime import datetime
from PIL import Image
from xml.etree.ElementTree import Element, SubElement
from xml.etree import ElementTree

# noinspection PyUnresolvedReferences
from xml.dom import minidom

imgList = []
nameList = []
pairing = []
matches = []
lines = 20
border = 10
spacer = 5
iterative = True
pageIterator = 0
page_creator = "user"
thread_count = 16

source = ""
dest = ""
gt_path = ""
image_path = ""
pred = False
debug = False

img_ext = '.nrm.png'
xmlSchemaLocation = \
    'http://schema.primaresearch.org/PAGE/gts/pagecontent/2017-07-15 ' \
    'http://schema.primaresearch.org/PAGE/gts/pagecontent/2017-07-15/pagecontent.xsd'


def main():
    tic = time.perf_counter()
    parser = make_parser()
    parse(parser.parse_args())

    # os.chdir(source)
    get_files()
    match_files()
    pages = list(chunks(matches, lines))
    pages = name_pages(pages)
    i = 0
    processes = []
    concurrency = thread_count
    print("Currently using " + str(concurrency) + " Thread(s)")
    sema = Semaphore(concurrency)
    for page in pages:
        sema.acquire()
        progress(i + 1, len(pages) * 2, "Processing page" + str(i + 1) + " of " + str(len(pages)))
        process = multiprocessing.Process(target=make_page, args=(page, sema,))
        processes.append(process)
        process.start()
        i += 1

    for process in processes:
        progress(i + 1, len(pages) * 2, "Finishing page " + str((i + 1) - len(pages)) + " of " + str(len(pages)))
        process.join()
        i += 1

    toc = time.perf_counter()
    print(f"\nFinished merging in {toc - tic:0.4f} seconds")
    print("\nPages have been stored at ", dest)


def make_parser():
    parser = argparse.ArgumentParser(description='python script to merge GT lines to page images and xml')
    parser.add_argument('-c',
                        '--creator',
                        action='store',
                        dest='creator',
                        default='user',
                        help='creator tag for page xml')
    parser.add_argument('-s',
                        '--source-folder',
                        action='store',
                        dest='source_path',
                        default=os.getcwd(),
                        help='Path to images and GT')
    parser.add_argument('-i',
                        '--images-folder',
                        action='store',
                        dest='image_path',
                        default="",
                        help='Path to images')
    parser.add_argument('-gt',
                        '--gt-folder',
                        action='store',
                        dest='gt_path',
                        default="",
                        help='Path to GT')
    parser.add_argument('-d',
                        '--dest-folder',
                        action='store',
                        dest='dest_path',
                        default=os.getcwd() + '/merged/',
                        help='Path to merge objects')

    parser.add_argument('-e',
                        '--ext',
                        action='store',
                        dest='img_ext',
                        default='.bin.png',
                        help='image extension')

    parser.add_argument('-p',
                        '--pred',
                        action='store_true',
                        dest='pred',
                        default=False,
                        help='Set Flag to also store .pred.txt')

    parser.add_argument('-l',
                        '--lines',
                        action='store',
                        dest='lines',
                        type=int,
                        default=20,
                        help='lines per page')

    parser.add_argument('-ls',
                        '--line-spacing',
                        action='store',
                        dest='spacing',
                        type=int,
                        default=5,
                        help='line spacing')

    parser.add_argument('-b',
                        '--border',
                        action='store',
                        dest='border',
                        type=int,
                        default=10,
                        help='border in px')
    parser.add_argument('--debug',
                        action='store_true',
                        dest='debug',
                        default=False,
                        help='prints debug xml')
    parser.add_argument('--threads',
                        action='store',
                        dest='thread_count',
                        type=int,
                        default=16,
                        help='Thread count to be used')
    return parser


def parse(args):
    global page_creator
    page_creator = args.creator
    global source
    source = args.source_path
    global dest
    dest = check_dest(args.dest_path)
    global img_ext
    img_ext = args.img_ext
    global pred
    pred = args.pred
    global lines
    lines = args.lines
    global spacer
    spacer = args.spacing
    global border
    border = args.border
    global debug
    debug = args.debug
    global image_path
    if not args.image_path == "":
        image_path = check_dest(args.image_path)
    else:
        image_path = source
    global gt_path
    if not args.gt_path == "":
        gt_path = check_dest(args.gt_path)
    else:
        gt_path = source
    global thread_count
    thread_count =args.thread_count


def get_files():
    global imgList
    imgList = [f for f in sorted(glob.glob(image_path + '*' + img_ext))]


def match_files():
    for img in imgList:
        name = strip_path(img.split('.')[0])
        gt_files_list = [f for f in glob.glob(gt_path + name + ".gt.txt")]
        if len(gt_files_list) > 0:
            nameList.append(name)
            pairing.append(img)
            gt_filename = gt_files_list[0]
            pairing.append(gt_filename)
            pairing.append(get_text(gt_filename))
            if pred:
                pred_file_list = [f for f in glob.glob(gt_path + name + ".pred.txt")]
                if len(pred_file_list) > 0:
                    pred_filename = pred_file_list[0]
                    pairing.append(pred_filename)
                    pairing.append(get_text(pred_filename))
                else:
                    print("WARNING: The File " + gt_path + name + ".pred.txt could not be found! Omitting line from page")
            matches.append(pairing.copy())
            pairing.clear()
        else:
            print("WARNING: The File " + gt_path + name + ".gt.txt could not be found! Omitting line from page")


def get_text(filename):
    with open(filename, 'r') as my_file:
        data = my_file.read().rstrip()
        return data


def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def check_dest(destination):
    if not os.path.exists(destination):
        print(destination + "dir not found, creating directory")
        os.mkdir(destination)
    if not destination.endswith(os.path.sep):
        destination += os.path.sep
    return destination


def make_page(page_with_name, semaphore):
    merged = merge_images(page_with_name[0])
    merged.save(dest + strip_path(page_with_name[1]) + img_ext)
    xml_tree = build_xml(page_with_name[0], page_with_name[1] + img_ext, merged.height, merged.width)
    if debug:
        print(prettify(xml_tree))
    xml = ElementTree.tostring(xml_tree, 'utf8', 'xml')
    myfile = open(dest + strip_path(page_with_name[1]) + ".xml", "wb")
    myfile.write(xml)
    myfile.close()
    semaphore.release()


def name_pages(pages):
    page_with_name = []
    pages_with_name = []
    page_iterator = 0
    for page in pages:
        if iterative:
            page_iterator += 1
            name = str(page_iterator).zfill(4)
        else:
            name = page[0][0].split(".")[0] + "-" + page[-1][0].split(".")[0]
        page_with_name.append(page)
        page_with_name.append(name)
        pages_with_name.append(page_with_name.copy())
        page_with_name.clear()
    return pages_with_name


def strip_path(path):
    return ntpath.basename(path)


def merge_images(page):
    """Merge list of images into one, displayed on top of each other
    :return: the merged Image object
    """

    img_list = []
    img_width = 0
    img_height = 0
    spacer_height = spacer * (len(page) - 1)

    for line in page:
        image = Image.open(line[0])
        (width, height) = image.size
        img_width = max(img_width, width)
        img_height += height
        img_list.append(image)
    #  img_ext: str
    if 'nrm' not in img_ext:
        result = Image.new('RGB', (img_width + border * 2, img_height + border * 2 + spacer_height), (255, 255, 255))
    else:
        result = Image.new('LA', (img_width + border * 2, img_height + border * 2 + spacer_height), "WHITE")
    before = border

    for img in img_list:
        result.paste(img, (border, before))
        before += img.size[1] + spacer
    return result


def build_xml(line_list, img_name, img_height, img_width):
    """Builds PageXML from list of images, with txt files corresponding to each one of them
    :return: the built PageXml[.xml] file
    """
    pcgts = Element('PcGts')
    pcgts.set('xmlns', 'http://schema.primaresearch.org/PAGE/gts/pagecontent/2017-07-15')
    pcgts.set('xmlns:xsi', 'http://www.w3.org/2001/XMLSchema-instance')
    pcgts.set('xsi:schemaLocation', xmlSchemaLocation)

    metadata = SubElement(pcgts, 'Metadata')
    creator = SubElement(metadata, 'Creator')
    creator.text = page_creator
    created = SubElement(metadata, 'Created')
    generated_on = datetime.now().isoformat()
    created.text = generated_on
    last_change = SubElement(metadata, 'LastChange')
    last_change.text = generated_on

    page = SubElement(pcgts, 'Page')
    page.set('imageFilename', img_name)
    page.set('imageHeight', str(img_height))
    page.set('imageWidth', str(img_width))

    text_region = SubElement(page, 'TextRegion')
    text_region.set('id', 'r0')
    text_region.set('type', 'paragraph')
    region_coords = SubElement(text_region, 'Coords')
    s = str(border)
    coord_string = s + ',' + s + ' ' + s + "," + str(img_height - border) \
        + ' ' + str(img_width - border) + ',' + str(img_height - border) \
        + ' ' + str(img_width - border) + ',' + s
    region_coords.set('points', coord_string)
    i = 1
    last_bottom = border
    for line in line_list:
        text_line = SubElement(text_region, 'TextLine')
        text_line.set('id', 'r0_l' + str(strip_path(line[0]).split('.')[0].zfill(3)))
        i += 1
        line_coords = SubElement(text_line, 'Coords')
        image = Image.open(line[0])
        (width, height) = image.size
        line_coords.set('points', make_coord_string(last_bottom, width, height))
        last_bottom += (height + spacer)
        line_gt_text = SubElement(text_line, 'TextEquiv')
        line_gt_text.set('index', str(0))
        unicode_gt = SubElement(line_gt_text, 'Unicode')
        unicode_gt.text = line[2]
        if pred:
            line_prediction_text = SubElement(text_line, 'TextEquiv')
            line_prediction_text.set('index', str(1))
            unicode_prediction = SubElement(line_prediction_text, 'Unicode')
            unicode_prediction.text = line[4]

    return pcgts


def make_coord_string(previous_lower_left, line_width, line_height):
    b = str(border)
    p = str(previous_lower_left)
    w = str(line_width + border)
    h = str(line_height + previous_lower_left)
    coord_string = b + ',' + p + ' ' + b + "," + h + ' ' + w + ',' + h + ' ' + w + ',' + p
    return coord_string


def prettify(elem):
    """Return a pretty-printed XML string for the Element.
    """
    rough_string = ElementTree.tostring(elem, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml("  ")


def progress(count, total, status=''):
    bar_len = 60
    filled_len = int(round(bar_len * count / float(total)))

    percents = round(100.0 * count / float(total), 1)
    bar = '█' * filled_len + '_' * (bar_len - filled_len)

    sys.stdout.write('[%s] %s%s ...%s\r' % (bar, percents, '%', status))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
