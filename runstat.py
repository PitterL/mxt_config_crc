import os
import sys
import argparse
import config_parser as mcp
import utils
from verbose import VerboseMessage as v

def runstat(args=None):
    parser = parse_args(args)
    aargs = args if args is not None else sys.argv[1:]
    args = parser.parse_args(aargs)
    print(args)

    if not args.filename and not args.scan:
        parser.print_help()
        return

    v.set(args.verbose)

    db_loader = mcp.RawConfigScanner()
    db = None

    path = args.database
    if path:
        if os.path.exists(path):
            db = db_loader.load(path)
            #v.msg(v.INFO, db.applymap(lambda x: '{:02X}'.format(x)))
        else:
            v.msg(v.INFO, 'No use database')

    path = args.scan
    if path:
        if os.path.exists(path):
            db = db_loader.scan(path)
            #v.msg(v.INFO, db.applymap(lambda x: '{:02X}'.format(x)))
            db_loader.save()
        else:
            v.msg(v.WARN, 'Un-exist scanning dir \'{:s}\''.format(path))

    path = args.filename
    if path:
        if os.path.exists(path):
            ex_type = path.rsplit('.', 1)[-1].lower()
            if ex_type == 'xcfg':
                # load xcfg
                xcfg = mcp.XcfgConfigParser()
                xcfg.load(path)
                xcfg.save(args.output)

                # save to raw
                builder = mcp.XcfgBuildRawFile(xcfg)
                if args.raw:
                    builder.load_db(db)
                    builder.rebuild_raw_data()
                    builder.save_raw_file(args.output)
            elif ex_type == 'txt':
                sep = args.sep
                cal = utils.Calculate_CRC(sep)
                cal.load_file(path)
            else:
                v.msg(v.ERR, 'Un-support file name \'{:s}\''.format(path))
        else:
            v.msg(v.WARN, 'Un-exist file name \'{:s}\''.format(path))

def parse_args(args=None):

    parser = argparse.ArgumentParser(
        prog='Maxtouch Config calculator',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Tools for parsing maxTouch config and calculating config crc')

    parser.add_argument('--version',
                        action='version', version='%(prog)s v1.2.5',
                        help='show version')

    parser.add_argument('-f', '--filename', required=False,
                        nargs='?',
                        default='',
                        metavar='XCFG|TXT',
                        help='where the \'XCFG|TXT\' file will be load')

    parser.add_argument('-r', '--raw', required=False,
                        action='store_true',
                        help='whether save out a \'RAW\' file')

    parser.add_argument('-sep', '--sep', required=False,
                        nargs='?',
                        default=None,
                        metavar='SEP',
                        help='Delimiters for \'Raw Block\' split() to data')

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

    parser.add_argument('-o', '--output',
                        type=int,
                        choices=(1,2),
                        default=1,
                        help='set the output config file version (1: Version 1; 2: higher version)')
    return parser

cmd = None
#cmd = r"-f .\test\test_v4.xcfg --raw -o 1".split()
#cmd = r"-s .\test\test.xcfg -o 2".split()
#cmd = ["-s", r".\test\test.xcfg\FW 1.1"]
#cmd = ["-f", r".\test\test_v3_new.xcfg", "--raw", "-o", "3"]
if __name__ == "__main__":
    runstat(cmd)
