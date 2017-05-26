import os
import functools
import pandas as pd
import re
import datetime

from verbose import VerboseMessage as v

__metaclass__ = type

class BaseConfigBlock(object):
    OBJECT_TITLE_NAME = ('object', 'instance', 'length', 'address', 'offset')
    BLOCK_NAME = ('comments', 'header_info', 'application_info', 'object_title', 'object_data')

    def __init__(self):
        self.blocks = {}
        pass

    def build_info_block(self, name, data):
        block = pd.Series(data=data, index=name)

        return block

    def build_object_title_block(self, title):
        title_new = pd.DataFrame(title, columns=self.OBJECT_TITLE_NAME[:len(title[0])])
        off = [0]
        off.extend(title_new['length'].cumsum()[:-1])
        title_new['offset'] = pd.Series(off)

        return title_new

    def set(self, name, val):
        if name in self.BLOCK_NAME:
            self.blocks[name] = val

    def get(self, name, default=None):
        if name in self.blocks.keys():
            return self.blocks[name]
        return default

    def clr(self, name=None):
        if not name:
            for name in self.blocks.keys():
                del self.blocks[name]
        else:
            if name in self.blocks.keys():
                del self.blocks[name]


class RawConfigParser(BaseConfigBlock):

    (RAW_FILE_HEADER_MAGIC_WORD,) = ("OBP_RAW V1",)
    #(RAW_HEADER, RAW_INFO_BLOCK, RAW_INFO_BLOCK_CRC, RAW_CONFIG_DATA_CRC, RAW_CONFIG_DATA) = range(5)

    # [RAW_INFO_BLOCK]
    (FAMILY_ID, VARIANT, VERSION, BUILD, MATRIX_X, MATRIX_Y, OBJECTS_NUM, INFO_BLOCK_CHECKSUM, CHECKSUM) = range(9)
    RAW_INFO_BLOCK_NAME = ('FAMILY_ID', 'VARIANT', 'VERSION', 'BUILD', 'MATRIX_X', 'MATRIX_Y', 'OBJECTS_NUM',
                           'INFO_BLOCK_CHECKSUM', 'CHECKSUM')

    # method
    (PARSE_FULL, PARSE_HEADER) = range(2)

    def __init__(self, **kwargs):
        super(RawConfigParser, self).__init__()
        if hasattr(kwargs, 'method'):
            self.method = kwargs['method']
        else:
            self.method = self.PARSE_FULL
        self.f = None

    def __del__(self):
        if hasattr(self, 'f'):
            self.close()

    def open(self, path):
        if path:
            if self.f:
                self.f.close()
            f = open(path, 'r')
            self.f = f

    def close(self):
        if self.f:
            self.f.close()
            self.f = None

    def check_magic_header(self, str1):
        if str1.strip() == self.RAW_FILE_HEADER_MAGIC_WORD:
            return True
        else:
            v.msg(v.ERR, 'Not a raw file, header comments{:s}'.format(str1))
            return False

    def load(self, path):

        self.open(path)

        if not self.f:
            return

        v.msg(v.INFO, path)

        comments = []
        object_info = []
        object_data = []

        #[RAW_FILE_HEADER_MAGIC_WORD]
        line = self.f.readline()
        if not self.check_magic_header(line):
            self.close()
            return

        comments.append(line)

        #[RAW_INFO_BLOCK]
        line = self.f.readline()
        version_info_data = list(map(functools.partial(int, base=16), line.split()))

        # INFO_BLOCK_CHECKSUM
        line = self.f.readline()
        version_info_data.append(int(line, 16))

        # CHECKSUM
        line = self.f.readline()
        version_info_data.append(int(line, 16))

        #[OBJECT_DATA]
        if self.method == self.PARSE_FULL:
            for line in self.f:
                raw = list(map(functools.partial(int, base=16), line.split()))
                object_info.append(raw[:3])    # title
                object_data.extend(raw[3:])     # data

        # list[string]
        self.set('comments', comments)

        # Series
        header_info = self.build_info_block(self.RAW_INFO_BLOCK_NAME, version_info_data)
        self.set('header_info', header_info)

        # list[OBJ_TITLE:DataFrame, OBJ_DATA:list[int]]
        if self.method == self.PARSE_FULL:
            object_title = self.build_object_title_block(object_info)
            self.set('object_title', object_title)
            self.set('object_data', object_data)

    def clear(self):
        super(RawConfigParser, self).clr()
        self.close()

class XcfgConfigParser(BaseConfigBlock):

    # [HEADER] Tag:
    (COMMENTS, VERSION_INFO_HEADER, APPLICATION_INFO_HEADER, OBJECT_DATA) = range(4)
    re_patterns = {
        COMMENTS: r'\[COMMENTS\]\n',
        VERSION_INFO_HEADER: r'\[VERSION_INFO_HEADER\]\n',
        APPLICATION_INFO_HEADER: r'\[APPLICATION_INFO_HEADER\]\n',
        OBJECT_DATA: r'\[[a-zA-Z_-]+(\d+) INSTANCE (\d+)\]'
    }

    # [COMMENTS]:
    (AUTHOR, DATE_TIME) = range(2)
    # [VERSION_INFO_HEADER]:
    (FAMILY_ID, VARIANT, VERSION, BUILD, VENDOR_ID, PRODUCT_ID, CHECKSUM, INFO_BLOCK_CHECKSUM) = range(8)
    INFO_BLOCK_NAME = ('FAMILY_ID', 'VARIANT', 'VERSION', 'BUILD', 'VENDOR_ID', 'PRODUCT_ID', 'CHECKSUM',
                           'INFO_BLOCK_CHECKSUM') ## should same name as raw
    # [APPLICATION_INFO_HEADER]:
    (APP_NAME, APP_VERSION) = range(2)
    # [OBJECT_DATA]
    #(OBJ_TITLE, OBJ_DATA) = range(2)

    EX_BLOCK_NAME = ('objects_num', 'calculated_crc',)

    def __init__(self):
        super(XcfgConfigParser, self).__init__()
        self.exblocks = {}
        self.path = None
        self.f = None

    def __del__(self):
        if hasattr(self, 'f'):
            if self.f:
                self.f.close()

    def open(self, path):
        if path:
            if self.f:
                self.f.close()

            self.f = open(path, 'r')
            self.path = path

    def set_ext(self, name, val):
        if name in self.EX_BLOCK_NAME:
            self.exblocks[name] = val

    def get_ext(self, name, default=None):
        if name in self.exblocks.keys():
            return self.exblocks[name]
        return default

    def get_path(self):
        return self.path

    def check_header(self, line):
        raw = line.strip()
        if raw.startswith('[') and raw.endswith(']'):
            for tag, ptn in self.re_patterns.items():
                re_tag = re.compile(ptn)
                result = re_tag.match(line)
                if result:
                    return tag, result

        return None, None

    def parse_comments(self, it):
        info = []
        line = None
        for line in it:
            if line.isspace():
                continue

            tag = self.check_header(line)[0]
            if tag:
                break

            info.append(line.strip())

        return info, line

    def parse_version_info(self, it):

        name = []
        data = []
        line = None
        for line in it:
            if line.isspace():
                continue

            tag = self.check_header(line)[0]
            if tag:
                break

            raw = line.strip().split('=')
            if len(raw) == 2:
                try:
                    val = int(raw[1], 0)
                except Exception as e:
                    v.msg(v.WARN, "Set Un-recognized value to zero: {:s}, Error = {:s}".format(line.strip(), str(e)))
                    val = 0
                finally:
                    name.append(raw[0].strip())
                    data.append(val)

        return name, data, line

    def parse_app_info(self, it):
        info = []
        line = None
        for line in it:
            if line.isspace():
                continue

            tag = self.check_header(line)[0]
            if tag:
                break

            info.append(line.strip())

        return info, line

    def parse_object_data(self, it):

        (address, size) = range(2)
        line = None

        #adress, size
        #   e.g:
        #       OBJECT_ADDRESS=214
        #       OBJECT_SIZE = 240
        info = []
        for i in range(2):
            line = next(it, None).strip()
            if not line:
                break

            raw = line.split('=')
            if len(raw) == 2:
                info.append(int(raw[1]))

        if len(info) != 2:
            return None, None, line

        #data
        #   e.g:
        #       0 1 DATA[0]=0
        #       1 1 DATA[1]=0
        #       ...
        data = []
        for i in range(info[size]):
            line = next(it, None).strip()
            if not line:
                break

            raw = line.split()
            if len(raw) == 3:
                offset = int(raw[0])
                length = int(raw[1])
                raw2 = raw[2].split('=')
                if len(raw2) == 2:
                    val = int(raw2[1])
                    for j in range(length):
                        data.append(val & 0xff)
                        val >>= 8

                if offset + length >= info[size]:
                    break
            else:
                break

        return info, data, line

    def load(self, path):
        self.open(path)

        if not self.f:
            return

        comments = []
        version_info_name = []
        version_info_data = []
        application_info = []
        object_info = []
        object_data = []

        self.xcfg_content = self.f.readlines()
        it = iter(self.xcfg_content)
        line = next(it, None)
        while line:
            if line.isspace():
                line = next(it, None)
                continue

            tag, result = self.check_header(line)
            if result:
                if tag is self.COMMENTS:
                    comments, line = self.parse_comments(it)
                elif tag is self.VERSION_INFO_HEADER:
                    version_info_name, version_info_data, line = self.parse_version_info(it)
                elif tag is self.APPLICATION_INFO_HEADER:
                    application_info, line = self.parse_app_info(it)
                elif tag is self.OBJECT_DATA:
                    if len(result.groups()) == 2:
                        obj = int(result.group(1))
                        ins = int(result.group(2))

                        info, val, line = self.parse_object_data(it)
                        (address, size) = range(2)
                        if len(info) == 2:
                            if len(val) == info[size]:
                                # OBJECT_TITLE_NAME
                                object_info.append([obj, ins, info[size], info[address]])
                                object_data.extend(val)
                        else:
                            v.msg(v.WARN, 'Mismatched object info, data: ', info, val)
                else:
                    v.msg(v.WARN, 'Unsupported tag: ', line)
            else:
                v.msg(v.WARN, 'Skip unknowns line: ', line)

            tag = self.check_header(line)[0]
            if not tag:
                line = next(it, None)
            else:
                v.msg(v.DEBUG2, 'Use former tag line: ', line)
                pass

        #end while

        #list[string]
        self.set('comments', comments)
        #Series
        if self.INFO_BLOCK_NAME != tuple(version_info_name):
            v.msg(v.INFO, 'Name mismatched, use block name:')
            v.msg(v.INFO, self.INFO_BLOCK_NAME)
            v.msg(v.INFO, version_info_name)

        header_info = self.build_info_block(self.INFO_BLOCK_NAME, version_info_data)
        self.set('header_info', header_info)

        #list[string]
        self.set('application_info', application_info)

        #list[OBJ_TITLE:DataFrame, OBJ_DATA:list[int]]
        object_title = self.build_object_title_block(object_info)
        self.set('object_title', object_title)
        self.set('object_data', object_data)

        objects_num = self.objects_num()
        self.set_ext('objects_num', objects_num)

        xCrc = XcfgCalculateCRC(self)
        calculated_crc = xCrc.calculate()
        self.set_ext('calculated_crc', calculated_crc)
        del xCrc

    def rebuild_checksum_header(self, lines, calculated_crc):

        key = self.INFO_BLOCK_NAME[self.CHECKSUM]
        excluded = self.INFO_BLOCK_NAME[self.INFO_BLOCK_CHECKSUM].split('_')[0]

        for idx, line in enumerate(lines):
            if line.isspace():
                continue

            tag = self.check_header(line)[0]
            if tag:
                break

            raw = line.strip().split('=')
            if len(raw) == 2:
                if key == raw[0].strip() and excluded not in line:
                    data = '{:s}=0x{:06X}\n'.format(key, calculated_crc)
                    return idx, data

        return None, None

    def save(self, path=None):

        if not self.xcfg_content:
            return

        if not path:
            path = self.get_path()

        calculated_crc = self.calculated_crc()
        config_crc = self.config_crc()

        if calculated_crc == config_crc:
            v.msg(v.INFO, 'Config CRC matched ({:06X}), Skip save xcfg file'.format(config_crc))
            return
        else:
            v.msg(v.WARN, 'Use Calculated CRC ({:06X}) overwrite File CRC({:06X})'.format(calculated_crc, config_crc))
            content = self.xcfg_content

            for i, line in enumerate(content):
                tag, result = self.check_header(line)
                if result:
                    if tag is self.COMMENTS:
                        pass
                    elif tag is self.VERSION_INFO_HEADER:
                        st = i + 1
                        end = st + len(self.INFO_BLOCK_NAME)
                        idx, data = self.rebuild_checksum_header(content[st:end], calculated_crc)
                        if idx is not None:
                            content[st + idx] = data
                            v.msg(v.DEBUG2, content[st:end])
                            break
                        else:
                            v.msg(v.ERR, 'Overwrite CRC failed, {:s} not found in header:'.format(self.INFO_BLOCK_NAME[self.CHECKSUM]))
                            v.msg(v.ERR, content[st:end])
                    elif tag is self.APPLICATION_INFO_HEADER:
                        break
                    elif tag is self.OBJECT_DATA:
                        break

        dir = os.path.dirname(path)
        name = os.path.basename(path)

        if not dir:
            dir = os.path.dirname(self.get_path())

        if not dir:
            dir = os.getcwd()

        if not name:
            name = os.path.basename(self.get_path())

        main, ext = name.rsplit('.')
        if not ext or ext == 'raw':
            ext = 'xcfg'

        now = datetime.datetime.now()
        basename = '.'.join([main, now.strftime('%Y%m%d_%H%M%S'), 'rebuild', ext])
        filename = os.path.join(dir, basename)
        v.msg(v.CONST, 'Save xcfg file to: {:s}'.format(filename))
        if os.path.exists(filename):
            os.remove(filename)

        with open(filename, 'w') as outfile:
            outfile.write(''.join(self.xcfg_content))
            #outfile.write('\n')
            outfile.close()

    def objects_num(self, default=0):

        num = default
        title = self.get('object_title')
        if title is not None:
            objects = set(title['object'])
            num = len(objects) + 2  #T9/T100 T6
            if 100 in objects:
                num += 1    #T44

        return num

    def info_crc(self, default=None):
        header = self.get('header_info')
        if header is not None and len(header) >= self.INFO_BLOCK_CHECKSUM:
            return header[self.INFO_BLOCK_CHECKSUM]

        return default

    def config_crc(self, default=None):
        header = self.get('header_info')
        if header is not None and len(header) >= self.CHECKSUM:
            return header[self.CHECKSUM]

        return default

    def calculated_crc(self, default=None):
        return self.get_ext('calculated_crc', default)

class XcfgCalculateCRC(object):

    def __init__(self, xcfg):
        self.xcfg = xcfg

    def load(self, path):
        self.xcfg.load(path)

    def __crc24(self, crc, byte0, byte1):

        crcpoly = 0x80001B

        data_word = (byte1 << 8) | byte0
        result = ((crc << 1) ^ data_word)

        if result & 0x1000000:
            result ^= crcpoly

        return result

    def __calculate_crc(self, data, start_off=None, end_off=None):

        ptr = data[start_off:end_off]

        v.msg(v.DEBUG2, 'calcualte crc: st={} end={} len={}'.format(start_off, end_off, len(ptr)))

        if not len(ptr):
            return 0

        if len(ptr) & 0x1:
            ptr.append(0)

        crc = 0
        for i in range(len(ptr) // 2):
            crc = self.__crc24(crc, ptr[i * 2], ptr[i * 2 + 1])

            # Mask to 24-bit
        crc &= 0x00FFFFFF

        return crc

    def calculate(self):
        header = self.xcfg.get('header_info')
        if header is None:
            return

        title = self.xcfg.get('object_title')
        data = self.xcfg.get('object_data')
        if title is None or data is None:
            return

        v.msg(v.DEBUG, header.apply(lambda x: '{:02X}'.format(x)))
        v.msg(v.DEBUG, title)
        v.msg(v.DEBUG, data)

        #search start position
        st = []
        for idx in title.index:
            t_info = title.loc[idx]
            if t_info['object'] == 7:
                st.append(t_info)
            elif t_info['object'] == 71:
                st.append(t_info)
                break

        if not len(st):
            v.msg(v.ERR, 'Missed T7 or T71 object, not CRC calculated')
            return

        start = st[-1]['offset']
        calculated_crc = self.__calculate_crc(data, start)
        matched = calculated_crc == header[self.xcfg.CHECKSUM]

        v.msg(v.CONST, 'CRC: calculate={:6X}, cfg={:6X} {:s}'.
              format(calculated_crc,
                     header[self.xcfg.CHECKSUM],
                     '(matched)' if matched else '(mismatch) X X X'))

        self.calculated_crc = calculated_crc

        return calculated_crc


class XcfgBuildRawFile(object):

    LOOKUP_DB_TABLE = [
        XcfgConfigParser.FAMILY_ID,
        XcfgConfigParser.VARIANT,
        XcfgConfigParser.VERSION,
        XcfgConfigParser.BUILD,
        XcfgConfigParser.INFO_BLOCK_CHECKSUM]

    def __init__(self, xcfg):
        self.xcfg = xcfg
        self.db = None

    def load_db(self, db):

        if not isinstance(db, pd.DataFrame):
            return

        name1 = tuple(db.columns.values)
        name2 = RawConfigParser.RAW_INFO_BLOCK_NAME[:RawConfigParser.CHECKSUM]
        if name1 != name2:
            v.msg(v.ERR, db.columns.values)
            v.msg(v.ERR, RawConfigParser.RAW_INFO_BLOCK_NAME)
            return

        if len(db.index):
            self.db = db.copy()

    def lookup_db(self, header):

        if self.db is None:
            return

        cond = []
        for idx in self.LOOKUP_DB_TABLE:
            cond.append('{:s}=={:d}'.format(header.index[idx], header[idx]))

        words = ' & '.join(cond)
        v.msg(v.DEBUG, words)
        result = self.db.query(words)
        if len(result):
            return result.iloc[0]
        else:
            return None

    def get_extra_info(self, header):

        result = self.lookup_db(header)
        if result is not None:
            #print(result.apply(lambda x: '{:02X}'.format(x)))
            ext = result[RawConfigParser.MATRIX_X], result[RawConfigParser.MATRIX_Y], result[RawConfigParser.OBJECTS_NUM]
        else:
            ext = [0, 0]
            v.msg(v.WARN, header.apply(lambda x: '{:02X}'.format(x)))
            v.msg(v.WARN, 'Please input the MATRIX_X/Y, format is <x, y>: ')
            v.msg(v.WARN, '## e.g. For \'336T\', input: 24,14')
            try:
                raw = input('input x,y: ')
                if len(raw) == 2:
                    ext = list(map(int, raw))
            except:
                v.msg(v.ERR, 'Input error({:s}), Use default (0,0) Matrix')

            num = self.xcfg.objects_num()
            v.msg(v.WARN, 'Please confirm object numbers: ({:d} default)'.format(num))
            try:
                raw = input('input object numbers: ')
                if len(raw) == 1:
                    num = int(raw)
            except:
                v.msg(v.ERR, 'Input error({:s}), Use default ({:d})', num)
            finally:
                ext.append(num)

        return ext

    def rebuild_raw_header_block(self, data, matrix_x, matrix_y, object_num):

        data_new = list(data[:RawConfigParser.BUILD + 1])
        data_new.extend([matrix_x, matrix_y, object_num])

        info_block = pd.Series(data=data_new, index=RawConfigParser.RAW_INFO_BLOCK_NAME[:len(data_new)])

        return info_block

    def rebuild_raw_data(self):

        xcfg = self.xcfg
        header = xcfg.get('header_info')
        if header is None:
            return

        title = xcfg.get('object_title')
        if title is None:
            return

        data = xcfg.get('object_data')
        if data is None:
            return

        v.msg(v.DEBUG, header.apply(lambda x: '{:02X}'.format(x)))
        v.msg(v.DEBUG, title)
        v.msg(v.DEBUG, data)

        lines = []

        #RAW_HEADER
        lines.append(RawConfigParser.RAW_FILE_HEADER_MAGIC_WORD)
        #RAW_INFO_BLOCK

        extra = self.get_extra_info(header)
        raw_header_block = self.rebuild_raw_header_block(header, *extra)
        raw = ' '.join('{:02X}'.format(x) for x in raw_header_block)
        lines.append(raw)
        #RAW_INFO_BLOCK_CRC
        raw = '{:06X}'.format(self.xcfg.info_crc(0))
        lines.append(raw)
        #RAW_CONFIG_DATA_CRC

        raw = '{:06X}'.format(self.xcfg.calculated_crc(0))
        lines.append(raw)
        #RAW_CONFIG_DATA

        for idx in title.index:
            info = title.loc[idx]
            if info['object'] == 37:
                continue

            trunk = []
            raw = '{:04X}'.format(info['object'])
            trunk.append(raw)
            raw = '{:04X}'.format(info['instance'])
            trunk.append(raw)
            raw = '{:04X}'.format(info['length'])
            trunk.append(raw)
            st = info['offset']
            end = info['offset'] + info['length']
            if end > len(data):
                print("Too long data request: ", info, len(data))
            raw = ' '.join('{:02X}'.format(x) for x in data[st: end])
            trunk.append(raw)
            lines.append(' '.join(trunk))

        v.msg(v.INFO, '\n'.join(lines))
        self.raw_content = lines

    def save_raw_file(self, path=None):
        xcfg = self.xcfg
        if xcfg is None:
            return

        if not path:
            path = xcfg.get_path()

        dir = os.path.dirname(path)
        name = os.path.basename(path)

        if not dir:
            dir = os.path.dirname(xcfg.get_path())

        if not dir:
            dir = os.getcwd()

        if not name:
            name = os.path.basename(xcfg.get_path())

        main, ext = name.rsplit('.')
        if not ext or ext == 'xcfg':
            ext = 'raw'

        now = datetime.datetime.now()
        basename = '.'.join([main, now.strftime('%Y%m%d_%H%M%S'), 'rebuild', ext])
        filename = os.path.join(dir, basename)
        if os.path.exists(filename):
            os.remove(filename)

        with open(filename, 'w') as outfile:
            outfile.write('\n'.join(self.raw_content))
            outfile.write('\n')
            outfile.close()
            v.msg(v.CONST, 'Save raw file to: {:s}'.format(filename))

class RawConfigScanner(RawConfigParser):

    PARAM = {'db_file': 'db_header.csv',
                'max_scan_files': 5000,
                'db_col': RawConfigParser.RAW_INFO_BLOCK_NAME[:RawConfigParser.CHECKSUM]}

    def __init__(self):
        super(RawConfigScanner, self).__init__()
        self.parser = RawConfigParser(method=RawConfigParser.PARSE_HEADER)
        self.db = pd.DataFrame(columns=self.PARAM['db_col'])
        self.db_file = os.path.join(os.getcwd(), self.PARAM['db_file'])
        self.db_new = False

    def load(self, path=None):
        try:
            if path is not None:
                self.db_file = path

            db = pd.read_csv(self.db_file)
            db.dropna(axis=0, how='any', inplace=True)
            self.db = db

            return db
        except Exception as e:
            v.msg(v.ERR, 'Unable to load db file: {:s}, Error = {:s}'.format(self.db_file, str(e)))

    def save(self):

        if not self.db_new:
            return

        if not isinstance(self.db, pd.DataFrame):
            return

        if len(self.db.index):
            try:
                self.db.drop_duplicates(keep='first', inplace=True)
                self.db.dropna(axis=0)
                if len(self.db):
                    self.db.to_csv(self.db_file, sep=',', index=False)
                    v.msg(v.CONST, 'Save db to file: {:s}'.format(self.db_file))
            except Exception as e:
                v.msg(v.ERR, 'Unable to save db file: {:s}, Error = {:s}'.format(self.db_file, str(e)))

        self.db_new = False

    def __search_header_in_dirs(self, path, limited=0):

        header_blocks = []
        paths = []
        i = 0
        for root, dirs, files in os.walk(path, topdown=True):
            for name in files:
                raw = name.split('.')
                if 'rebuild' not in raw and 'raw' == raw[-1]:
                    if 'rebuild' in raw:
                        v.msg(v.INFO, 'skip rebuild file: {:s}({:s})'.format(name, root))
                    else:
                        path = os.path.join(root, name)
                        try:
                            self.parser.load(path)
                            info = self.parser.get('header_info')
                            if info is not None:
                                #header_info = list(info).append(path)
                                header_info = info[:self.INFO_BLOCK_CHECKSUM + 1]
                                header_blocks.append(header_info)
                                paths.append(path)
                        except Exception as e:
                            v.msg(v.ERR, 'Parse failed: {:s}'.format(str(e)))
                        finally:
                            self.clear()

            #for name in dirs:
                #print('scan dirs: {:s}'.format(os.path.join(root, name)))

        return header_blocks, paths

    def __query_select_duplicate(self, db_header, header, extra):
        v.msg(v.WARN, '<1> Database: ', ' '.join(map(lambda x: '{:02X}'.format(x), db_header)))
        v.msg(v.WARN, '<2> Current new file: ', ' '.join(map(lambda x: '{:02X}'.format(x), header)), '({})'.format(extra))
        try:
            raw = input('Select keep which? -- 1(Keep database - default) , 2(Use new) 3 (Discard both): ').strip()

            if '3' == raw:
                return None
            if '2' == raw:
                return header
            else:
                return db_header
        except:
            print('Invalid input selct, use default 1')
            return db_header

    def __check_duplicate_and_update(self, db_list, header, extra=None):

        for i, db_header in enumerate(db_list):
            if header[:self.BUILD + 1] == db_header[:self.BUILD + 1]:
                if header == db_header:
                    return
                else:
                    selected = self.__query_select_duplicate(db_header, header, extra)
                    print(selected)
                    if selected == header:
                        db_list[i] = selected
                        return selected
                    elif selected is None:
                        db_list.pop(i)

                    return

        v.msg(v.DEBUG2, tuple(map(lambda x: '{:02x}'.format(x), header)))
        db_list.append(header)

        return header

    def scan(self, path):

        db_list = self.db.values.tolist()
        new_list = []
        if os.path.exists(path):
            header_blocks, paths = self.__search_header_in_dirs(path)
            for i, header in enumerate(header_blocks):
                new_header = self.__check_duplicate_and_update(db_list, list(header.values), paths[i])
                if new_header is not None:
                    v.msg(v.DEBUG2, new_header)
                    new_list.append(new_header)
        else:
            v.msg(v.ERR, 'Unexist path: {:s}'.format(path))

        if new_list:
            v.msg(v.INFO, 'add new {:d} headers: '.format(len(new_list)))
            v.msg(v.DEBUG, pd.DataFrame(new_list, columns=self.db.columns).applymap(lambda x: '{:02X}'.format(x)))

            self.db = pd.DataFrame(db_list, columns=self.db.columns)
            self.db.sort_values(by=list(self.db.columns.values), inplace=True)
            self.db.drop_duplicates(inplace=True)
            self.db_new = True

        return self.db
