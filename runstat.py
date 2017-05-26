import os
import sys
import argparse
import config_parser as mcp
from verbose import VerboseMessage

def runstat(args=None):
    parser = parse_args(args)
    aargs = args if args is not None else sys.argv[1:]
    args = parser.parse_args(aargs)
    print(args)

    if not args.filename and not args.scan:
        parser.print_help()
        return

    VerboseMessage.set(args.verbose)

    if not args.filename and not args.scan:
        args.print_help()
        return

    db_loader = mcp.RawConfigScanner()
    db = None

    path = args.database
    if path and os.path.exists(path):
        db_loader.load(path)
        # print(db.applymap(lambda x: '{:02X}'.format(x)))

    path = args.scan
    if path and os.path.exists(path):
        db = db_loader.scan(path)
        # print(db.applymap(lambda x: '{:02X}'.format(x)))
        db_loader.save()

    path = args.filename
    if path and os.path.exists(path):
        # load xcfg
        xcfg = mcp.XcfgConfigParser()
        xcfg.load(path)
        xcfg.save()

        # save to raw
        builder = mcp.XcfgBuildRawFile(xcfg)
        builder.load_db(db)
        builder.rebuild_raw_data()
        builder.save_raw_file()

def parse_args(args=None):

    parser = argparse.ArgumentParser(
        prog='xparse',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Tools for parsing maxTouch config and calculating config crc')

    parser.add_argument('--version',
                        action='version', version='%(prog)s v1.0.0',
                        help='show version')

    parser.add_argument('-f', '--filename', required=False,
                        nargs='?',
                        default='',
                        metavar='XCFG',
                        help='where the \'XCFG\' file will be load')

    parser.add_argument('-s', '--scan', required=False,
                        nargs='?',
                        default='',
                        const='.',
                        metavar='DIR',
                        help='Path will be scanned to build chip Info Block database')

    parser.add_argument('-db', '--database', required=False,
                        nargs='?',
                        default='db_header.csv',
                        help='load chip Info Block database')
    """
    parser.add_argument('-e', '--extra', required=False,
                        #metavar=('<X>', '<Y>', '<OBJ number>'),
                        nargs='*',
                        type=int,
                        default=None,
                        help='Chip Info Block information: <MAXTRIX_X> <MAXTRIX_Y> [OBJECTS_NUM]')
    """
    parser.add_argument('-v', '--verbose',
                        type=int,
                        choices=range(5),
                        default=1,
                        help='set debug verbose level[0-5]')

    return parser



#cmd = r"-s -f D:\temp\temp\1.xcfg -db D:\temp\temp\db_header.csv".split()
cmd = None
if __name__ == "__main__":

    runstat(cmd)
