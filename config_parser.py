import os
import sys
import functools
import pandas as pd
import re
import datetime

from verbose import VerboseMessage as v

__metaclass__ = type

class BaseConfigBlock(object):
    """Shared container helpers for parsed config/header/object blocks."""

    OBJECT_TITLE_NAME = ('object', 'instance', 'length', 'address', 'offset')
    BLOCK_NAME = ('comments', 'header_info', 'file_info', 'application_info', 'object_title', 'object_data')

    def __init__(self):
        """Initialize the in-memory block storage.

        Input:
            None.
        Output:
            None. Creates an empty dictionary used by parser subclasses.
        """
        self.blocks = {}
        pass

    def build_info_block(self, name, data):
        """Build a pandas Series for header-style name/value blocks.

        Input:
            name: Iterable of field names.
            data: Iterable of values aligned with the field names.
        Output:
            pandas.Series containing the supplied values indexed by field name.
        """
        block = pd.Series(data=data, index=name)

        return block

    def build_object_title_block(self, title):
        """Build an object-title table and derive cumulative offsets.

        Input:
            title: List of object metadata rows.
        Output:
            pandas.DataFrame with object, instance, length, address, and offset.

        Key steps:
            1. Convert raw rows into a DataFrame.
            2. Derive each object's byte offset from the cumulative length column.
        """
        title_new = pd.DataFrame(title, columns=self.OBJECT_TITLE_NAME[:len(title[0])])
        off = [0]
        off.extend(title_new['length'].cumsum()[:-1])
        title_new['offset'] = pd.Series(off)    #object offset in memory

        return title_new

    def set(self, name, val):
        """Store a parsed block by its well-known block name.

        Input:
            name: Registered block key.
            val: Parsed block value.
        Output:
            None. Updates the internal block dictionary when the key is allowed.
        """
        if name in self.BLOCK_NAME:
            self.blocks[name] = val

    def get(self, name, default=None):
        """Read a parsed block from the internal block dictionary.

        Input:
            name: Registered block key.
            default: Fallback value when the block is absent.
        Output:
            Stored block value or the provided default.
        """
        if name in self.blocks.keys():
            return self.blocks[name]
        return default

    def clr(self, name=None):
        """Clear one parsed block or all parsed blocks.

        Input:
            name: Optional block key to clear. When omitted, all blocks are removed.
        Output:
            None. Mutates the internal block dictionary in place.
        """
        if not name:
            for name in self.blocks.keys():
                del self.blocks[name]
        else:
            if name in self.blocks.keys():
                del self.blocks[name]


class RawConfigParser(BaseConfigBlock):
    """Parser for Microchip raw configuration files across V1/V3/V4 formats."""

    (RAW_VERSION_NONE, RAW_VERSION_1, RAW_VERSION_3, RAW_VERSION_4) = (0, 1, 3, 4)

    (RAW_FILE_HEADER_MAGIC_WORD, RAW_FILE_HEADER_MAGIC_WORD_V3, RAW_FILE_HEADER_MAGIC_WORD_V4) = ("OBP_RAW V1", "OBP_RAW V3", "OBP_RAW V4")
    #(RAW_HEADER, RAW_INFO_BLOCK, RAW_INFO_BLOCK_CRC, RAW_CONFIG_DATA_CRC, RAW_CONFIG_DATA) = range(5)

    # [RAW_INFO_BLOCK]
    (FAMILY_ID, VARIANT, VERSION, BUILD, MATRIX_X, MATRIX_Y, OBJECTS_NUM, INFO_BLOCK_CHECKSUM, CHECKSUM) = range(9)
    RAW_INFO_BLOCK_NAME = ('FAMILY_ID', 'VARIANT', 'VERSION', 'BUILD', 'MATRIX_X', 'MATRIX_Y', 'OBJECTS_NUM',
                           'INFO_BLOCK_CHECKSUM', 'CHECKSUM')

    # method
    (PARSE_FULL, PARSE_HEADER) = range(2)

    def __init__(self, **kwargs):
        """Configure the raw parser and choose header-only or full parsing mode.

        Input:
            kwargs: Optional method selection, e.g. PARSE_FULL or PARSE_HEADER.
        Output:
            None. Initializes parser mode and file handle state.
        """
        super(RawConfigParser, self).__init__()
        if hasattr(kwargs, 'method'):
            self.method = kwargs['method']
        else:
            self.method = self.PARSE_FULL
        self.f = None

    def __del__(self):
        """Ensure the underlying file handle is closed during object cleanup."""
        if hasattr(self, 'f'):
            self.close()

    def open(self, path):
        """Open a raw config file for reading.

        Input:
            path: Raw file path.
        Output:
            None. Replaces the active file handle when the file can be opened.
        """
        if path:
            if self.f:
                self.f.close()
            f = open(path, 'r')
            self.f = f

    def close(self):
        """Close the active raw file handle when present."""
        if self.f:
            self.f.close()
            self.f = None

    def check_magic_header(self, str1):
        """Detect the raw file version from the first header line.

        Input:
            str1: First line from a raw file.
        Output:
            Integer raw-version constant or 0 when the header is unsupported.
        """
        if str1.strip() == self.RAW_FILE_HEADER_MAGIC_WORD:
            return RawConfigParser.RAW_VERSION_1
        if str1.strip() == self.RAW_FILE_HEADER_MAGIC_WORD_V3:
            return RawConfigParser.RAW_VERSION_3
        if str1.strip() == self.RAW_FILE_HEADER_MAGIC_WORD_V4:
            return RawConfigParser.RAW_VERSION_4
        else:
            v.msg(v.ERR, 'Not a raw file, header comments{:s}'.format(str1))
            return RawConfigParser.RAW_VERSION_0

    def load(self, path):
        """Parse a raw file into header/object blocks.

        Input:
            path: Path to the raw file.
        Output:
            None. Parsed content is stored into this instance via BaseConfigBlock.

        Key steps:
            1. Read the raw version header and optional V3/V4 metadata lines.
            2. Parse the info block and CRC lines.
            3. Optionally read and flatten object records when full parsing is enabled.
        """

        self.open(path)

        if not self.f:
            return

        v.msg(v.INFO, path)

        comments = []
        object_info = []
        object_data = []

        #[RAW_FILE_HEADER_MAGIC_WORD]
        line = self.f.readline()
        ver = self.check_magic_header(line)

        if not ver:
            v.msg(v.ERR, 'Non-supported raw file')
            self.close()
            return

        comments.append(line)

        if ver >= RawConfigParser.RAW_VERSION_3:
            #[ENCRYPTION]
            line = self.f.readline()
            if line.split()[1] != '0':
                v.msg(v.ERR, 'Encrypted raw file')
                return

            # [MAX_ENCRYPTION_BLOCKS]
            # drop it
            self.f.readline()

        if ver >= RawConfigParser.RAW_VERSION_4:
            #[NO_DEVICES]
            # drop it
            self.f.readline()

        #[RAW_INFO_BLOCK]
        line = self.f.readline()
        version_info_datas = list(map(functools.partial(int, base=16), line.split()))

        # INFO_BLOCK_CHECKSUM
        line = self.f.readline()
        version_info_datas.append(int(line, 16))

        # CHECKSUM
        line = self.f.readline()
        version_info_datas.append(int(line, 16))

        # DEVICE_0
        if ver >= RawConfigParser.RAW_VERSION_4:
            # `[DEVICE_0]`
            # drop it
            self.f.readline()

        #[OBJECT_DATA]
        if self.method == self.PARSE_FULL:
            for line in self.f:
                raw = list(map(functools.partial(int, base=16), line.split()))
                object_info.append(raw[:3])    # title
                object_data.extend(raw[3:])     # data

        # list[string]
        self.set('comments', comments)

        # Series
        header_info = self.build_info_block(self.RAW_INFO_BLOCK_NAME, version_info_datas)
        self.set('header_info', header_info)

        # list[OBJ_TITLE:DataFrame, OBJ_DATA:list[int]]
        if self.method == self.PARSE_FULL:
            object_title = self.build_object_title_block(object_info)
            self.set('object_title', object_title)
            self.set('object_data', object_data)

    def clear(self):
        """Clear parsed raw blocks and close the current file handle."""
        super(RawConfigParser, self).clr()
        self.close()

class XcfgConfigParser(BaseConfigBlock):
    """Parser and writer for Microchip Studio XCFG files, including payload sections."""

    # [HEADER] Tag:
    (T_COMMENTS, T_VERSION_INFO_HEADER, T_FILE_INFO_HEADER, T_APPLICATION_INFO_HEADER, T_DEVICE, T_PAYLOAD_DATA, T_OBJECT_DATA, D_OBJ_VALUE) = range(8)

    tag_re_patterns = {
        T_COMMENTS: r'\[COMMENTS\]',
        T_VERSION_INFO_HEADER: r'\[VERSION_INFO_HEADER\]',
        T_FILE_INFO_HEADER:  r'\[FILE_INFO_HEADER\]',
        T_APPLICATION_INFO_HEADER: r'\[APPLICATION_INFO_HEADER\]',
        T_DEVICE: r'\[(DEVICE_[0-9])\]',
        T_PAYLOAD_DATA: r'\[(T68_SERIALDATACOMMAND_PAYLOAD_[^\]]+)\]',
        T_OBJECT_DATA: r'\[[a-zA-Z_-]+(\d+)[ \t]+INSTANCE[ \t]+(\d+)\]',
    }
    dat_re_patterns = {
        D_OBJ_VALUE: r'(\d+)[ \t]+(\d+)[ \t]+([^=]+)=(-?\d+)',
    }

    # [COMMENTS]:
    (AUTHOR, DATE_TIME) = range(2)
    # [VERSION_INFO_HEADER]:
    (FAMILY_ID, VARIANT, VERSION, BUILD, VENDOR_ID, PRODUCT_ID, CHECKSUM, INFO_BLOCK_CHECKSUM) = range(8)
    INFO_BLOCK_NAME = ('FAMILY_ID', 'VARIANT', 'VERSION', 'BUILD', 'VENDOR_ID', 'PRODUCT_ID', 'CHECKSUM',
                           'INFO_BLOCK_CHECKSUM') ## should same name as raw

    INFO_BLOCK_NAME_EXTRA_FIELDS = {
        3: ('MATRIX_X', 'MATRIX_Y', 'NO_OBJECTS'),
        4: ('MATRIX_X', 'MATRIX_Y', 'NO_OBJECTS', 'NO_DEVICES'),
    }
    """    
    (FAMILY_ID_V3, VARIANT_V3, VERSION_V3, BUILD_V3, MATRIX_X_V3, MATRIX_Y_V3, NO_OBJECTS_V3, VENDOR_ID_V3, PRODUCT_ID_V3, CHECKSUM_V3, INFO_BLOCK_CHECKSUM_V3) = range(11)
    INFO_BLOCK_NAME_V3 = ('FAMILY_ID', 'VARIANT', 'VERSION', 'BUILD', 'MATRIX_X', 'MATRIX_Y', 'NO_OBJECTS', 'VENDOR_ID', 'PRODUCT_ID', 'CHECKSUM',
                        'INFO_BLOCK_CHECKSUM') ## should same name as raw
    
    (FAMILY_ID_V4, VARIANT_V4, VERSION_V4, BUILD_V4, MATRIX_X_V4, MATRIX_Y_V4, NO_OBJECTS_V4, NO_DEVICES_V4, VENDOR_ID_V4, PRODUCT_ID_V4, CHECKSUM_V4, INFO_BLOCK_CHECKSUM_V4) = range(12)
    INFO_BLOCK_NAME_V4 = ('FAMILY_ID', 'VARIANT', 'VERSION', 'BUILD', 'MATRIX_X', 'MATRIX_Y', 'NO_OBJECTS', 'NO_DEVICES', 'VENDOR_ID', 'PRODUCT_ID', 'CHECKSUM_DEVICE_0',
                    'INFO_BLOCK_CHECKSUM') ## should same name as raw
    """

    # [APPLICATION_INFO_HEADER]:
    #(APP_NAME, APP_VERSION) = range(2)
    # [OBJECT_DATA]
    #(OBJ_TITLE, OBJ_DATA) = range(2)

    EX_BLOCK_NAME = ('objects_num', 'calculated_crc', 'header_size', 'header_ext_data', 'version_info', 'file_version', 'device_name', 'payload_sections')

    def __init__(self):
        """Initialize parser state, extension storage, and file-handle fields."""
        super(XcfgConfigParser, self).__init__()
        self.exblocks = {}
        self.path = None
        self.f = None

    def __del__(self):
        """Close the opened XCFG file during object cleanup when needed."""
        if hasattr(self, 'f'):
            if self.f:
                self.f.close()

    def open(self, path):
        """Open an XCFG file in binary mode and remember its path.

        Input:
            path: Path to an xcfg file.
        Output:
            None. Updates self.f and self.path when a path is provided.
        """
        if path:
            if self.f:
                self.f.close()

            self.f = open(path, 'rb')
            self.path = path

    def decode(self, line):
        """Decode binary file content into UTF-8 text when required.

        Input:
            line: bytes or str value.
        Output:
            Decoded str value.
        """
        if isinstance(line, bytes):
            return line.decode('utf-8')
        else:
            return line

    def encode(self, line):
        """Encode text back into UTF-8 bytes when required.

        Input:
            line: str or bytes value.
        Output:
            Encoded bytes value.
        """
        if isinstance(line, str):
            return line.encode('utf-8')
        else:
            return line

    def strip(self, line):
        """Remove BOM characters and surrounding whitespace from a line.

        Input:
            line: Raw text line from the xcfg file.
        Output:
            Sanitized string without BOM prefix or surrounding whitespace.
        """
        for i, a in enumerate(line):
            # studio xcfg with utf-8 will has this head
            if a != '\ufeff':
                break

        raw = line[i:]
        return raw.strip()

    def set_ext(self, name, val):
        """Store parser extension metadata that does not belong to BaseConfigBlock.

        Input:
            name: Known extension key.
            val: Value to store under that key.
        Output:
            None. Updates self.exblocks when the key is allowed.
        """
        if name in self.EX_BLOCK_NAME:
            self.exblocks[name] = val

    def get_ext(self, name, default=None):
        """Read extension metadata collected during parsing or export.

        Input:
            name: Extension key.
            default: Fallback when the key is missing.
        Output:
            Stored extension value or the provided default.
        """
        if name in self.exblocks.keys():
            return self.exblocks[name]
        return default

    def get_path(self):
        """Return the currently loaded xcfg path."""
        return self.path

    def check_header(self, line):
        """Match a line against known XCFG section headers.

        Input:
            line: Candidate xcfg line.
        Output:
            Tuple of (tag_id, regex_match) or (None, None).
        """
        raw = self.strip(line)
        if raw.startswith('[') and raw.endswith(']'):
            for tag, ptn in self.tag_re_patterns.items():
                re_tag = re.compile(ptn)
                result = re_tag.match(raw)
                if result:
                    return tag, result

        return (None, None)

    def check_data(self, line):
        """Match a line against known XCFG data-row patterns.

        Input:
            line: Candidate xcfg line.
        Output:
            Tuple of (data_tag_id, regex_match) or (None, None).
        """
        raw = self.strip(line)
        for tag, ptn in self.dat_re_patterns.items():
            re_tag = re.compile(ptn)
            result = re_tag.match(raw)
            if result:
                return tag, result

        return (None, None)

    def parse_comments(self, it):
        """Parse the free-form [COMMENTS] section.

        Input:
            it: Iterator over xcfg lines positioned after the header tag.
        Output:
            Tuple of (comment_lines, next_header_line).
        """
        info = []
        line = None
        for line in it:
            if line.isspace():
                continue

            tag, _ = self.check_header(line)
            if tag:
                break

            info.append(line.strip())

        return info, line


    def parse_name_value_pairs(self, it):
        """Parse simple NAME=VALUE sections into parallel name/value arrays.

        Input:
            it: Iterator over xcfg lines positioned after a section header.
        Output:
            Tuple of (name_list, value_list, next_header_line).

        Key steps:
            1. Stop when the next section header is encountered.
            2. Normalize booleans and integers.
            3. Replace malformed numeric values with 0 and log a warning.
        """
        name = []
        data = []
        line = None
        for line in it:
            if line.isspace():
                continue

            tag, _ = self.check_header(line)
            if tag:
                break

            raw = line.strip().split('=')
            if len(raw) == 2:
                try:
                    s = raw[1].strip().lower()
                    if s in ('false', 'true'):
                        val = (s == 'true')
                    else:
                        val = int(s, 0)
                except Exception as e:
                    v.msg(v.WARN, "Found Non-Number value at line: `{:s}`, Error = `{:s}`. Set Value to 0".format(line.strip(), str(e)))
                    val = 0 #raw[1]
                finally:
                    name.append(raw[0].strip())
                    data.append(val)

        return name, data, line

    def parse_version_info(self, it):
        """Parse the [VERSION_INFO_HEADER] body.

        Input:
            it: Iterator over xcfg lines.
        Output:
            Same tuple format as parse_name_value_pairs.
        """
        return self.parse_name_value_pairs(it)

    def parse_file_info(self, it):
        """Parse the [FILE_INFO_HEADER] body.

        Input:
            it: Iterator over xcfg lines.
        Output:
            Same tuple format as parse_name_value_pairs.
        """
        return self.parse_name_value_pairs(it)

    def parse_app_info(self, it):
        """Parse the [APPLICATION_INFO_HEADER] body.

        Input:
            it: Iterator over xcfg lines.
        Output:
            Tuple of (application_info_lines, next_header_line).
        """
        info = []
        line = None
        for line in it:
            if line.isspace():
                continue

            tag, _ = self.check_header(line)
            if tag:
                break

            info.append(line.strip())

        return info, line

    def parse_device_data(self, it):
        """Parse device-specific header fields that follow [DEVICE_n].

        Input:
            it: Iterator over xcfg lines.
        Output:
            Same tuple format as parse_name_value_pairs.
        """
        return self.parse_name_value_pairs(it)

    def parse_payload_data(self, it, section_name):
        """Parse a T68 payload section and preserve its metadata and bytes.

        Input:
            it: Iterator over xcfg lines positioned after the payload header.
            section_name: Payload section tag name.
        Output:
            Tuple of (payload_dict, next_header_line).

        Key steps:
            1. Read payload checksum/size fields.
            2. Expand packed integer DATA rows into little-endian bytes.
            3. Pad or truncate to the declared payload size.
        """
        line = None
        payload = {
            'name': section_name,
            'checksum': 0,
            'size': 0,
            'data': [],
        }

        for line in it:
            if line is None:
                break

            if line.isspace():
                continue

            tag, _ = self.check_header(line)
            if tag:
                break

            data_tag, match = self.check_data(line)
            if data_tag is self.D_OBJ_VALUE:
                length = int(match.group(2))
                value = int(match.group(4))
                for _ in range(length):
                    payload['data'].append(value & 0xff)
                    value >>= 8
                continue

            raw = line.strip().split('=', 1)
            if len(raw) != 2:
                continue

            name = raw[0].strip()
            try:
                value = int(raw[1].strip(), 0)
            except Exception as error:
                v.msg(v.WARN, "Invalid payload field at line `{:s}`, Error=`{:s}`".format(line.strip(), str(error)))
                continue

            if name == 'PAYLOAD_CHECKSUM':
                payload['checksum'] = value
            elif name == 'PAYLOAD_SIZE':
                payload['size'] = value

        size = payload['size']
        data = payload['data']
        if size:
            if len(data) < size:
                data.extend([0] * (size - len(data)))
            elif len(data) > size:
                payload['data'] = data[:size]

        return payload, line

    def parse_object_data(self, it):
        """Parse one object section's address, size, and flattened data bytes.

        Input:
            it: Iterator over xcfg lines positioned after an object header.
        Output:
            Tuple of (info_list, data_bytes, next_header_line).

        Key steps:
            1. Read OBJECT_ADDRESS and OBJECT_SIZE.
            2. Expand each packed value row into little-endian bytes.
            3. Stop on malformed rows or when the declared size is reached.
        """

        (address, size) = range(2)
        line = None

        #adress, size
        #   e.g:
        #       OBJECT_ADDRESS=214
        #       OBJECT_SIZE = 240
        info = []
        for i in range(2):
            line = next(it, None)
            if line is None:
                break

            line = line.strip()
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
            line = next(it, None)
            if line is None:
                break

            line = line.strip()
            if not line:
                break

            tag, _ = self.check_data(line)
            if tag is not self.D_OBJ_VALUE:
                print("data crashed at OBJECT_ADDRESS[{}] OBJECT_SIZE[{}]: {}".format(info[address], info[size], data))
                if len(line.split('=')) != 2:
                    break

            raw = line.split()
            if len(raw) == 3:
                try:
                    offset = int(raw[0])
                    length = int(raw[1])
                    raw2 = raw[2].split('=')
                    if len(raw2) == 2:
                        val = int(raw2[1])
                        for j in range(length):
                            data.append(val & 0xff)
                            val >>= 8
                except Exception as error:
                    print('Parse data line failed', line, error)
                    break

                if offset + length >= info[size]:
                    break
            else:
                break

        return info, data, line

    def extract_info_block(self, header, file_ver):
        """Remove version-specific extra fields from the main header series.

        Input:
            header: pandas.Series for the version header.
            file_ver: Parsed xcfg version.
        Output:
            List of removed extra-field values in declared order.
        """
        ext = []

        if file_ver in XcfgConfigParser.INFO_BLOCK_NAME_EXTRA_FIELDS.keys():
            for item in XcfgConfigParser.INFO_BLOCK_NAME_EXTRA_FIELDS[file_ver]:
                if item in header:
                    ext.append(header.pop(item))

        return ext

    def load(self, path):
        """Parse an xcfg file, calculate CRC, and store all derived blocks.

        Input:
            path: Path to the xcfg file.
        Output:
            None. Parsed data is stored on the parser instance.

        Key steps:
            1. Walk through headers using a state-machine loop.
            2. Parse standard blocks, object data, and payload sections.
            3. Build header/object tables and calculate the configuration CRC.
        """
        self.open(path)

        if not self.f:
            return

        comments = []
        version_info_names = []
        version_info_datas = []
        application_info = []
        object_info = []
        object_data = []
        payload_sections = []
        device_name = None
        file_info_names = None

        self.xcfg_content = list(map(self.decode, self.f.readlines()))
        it = iter(self.xcfg_content)
        line = next(it, None)
        while line:
            if line.isspace():
                line = next(it, None)
                continue

            tag, result = self.check_header(line)
            if result:
                if tag is self.T_COMMENTS:
                    comments, line = self.parse_comments(it)
                elif tag is self.T_VERSION_INFO_HEADER:
                    version_info_names, version_info_datas, line = self.parse_version_info(it)
                elif tag is self.T_FILE_INFO_HEADER:
                    file_info_names, file_info_datas, line = self.parse_file_info(it)
                elif tag is self.T_APPLICATION_INFO_HEADER:
                    application_info, line = self.parse_app_info(it)
                elif tag is self.T_DEVICE:
                    _, _, line = self.parse_device_data(it)
                    device_name = result[1]
                    # remove the device name in version_info_names
                    for i, name in enumerate(version_info_names):
                        if device_name in name:
                            version_info_names[i] = name.replace("_" + device_name, "")
                            break
                elif tag is self.T_PAYLOAD_DATA:
                    payload, line = self.parse_payload_data(it, result.group(1))
                    if payload is not None:
                        payload_sections.append(payload)
                elif tag is self.T_OBJECT_DATA:
                    if len(result.groups()) == 2:
                        obj = int(result.group(1))
                        ins = int(result.group(2))

                        info, data, line = self.parse_object_data(it)
                        (address, size) = range(2)
                        if len(info) == 2:
                            if len(data) != info[size]:
                                print("data size mismatch(expect {}, actual {}), crc calcalation may error".format(
                                    info[size], len(data)))
                                # if termined unexpected, filled zero
                                left = info[size] - len(data)
                                if left > 0:
                                    pad = [0] * left
                                    print('data not enough, filled {} zero at address'.format(left), info, ":", data, pad)
                                    data.extend(pad)
                                else:
                                    print('data overlap, trunk size {}'.format(left), info, data)
                                    data = data[:info[size]]

                            # OBJECT_TITLE_NAME
                            object_info.append([obj, ins, info[size], info[address]])
                            object_data.extend(data)
                        else:
                            v.msg(v.WARN, 'Mismatched object info, data: ', info, data)
                else:
                    v.msg(v.WARN, 'Unsupported tag: ', line)
            else:
                v.msg(v.WARN, 'Skip unknowns line: ', line)

            tag, _ = self.check_header(line)
            if not tag:
                line = next(it, None)
            else:
                v.msg(v.DEBUG2, 'Use former tag line: ', line)
                pass

        #end while

        # Save Comments
        self.set('comments', comments)
        # Save Version info
        verinfo = tuple(version_info_names)
        self.set_ext('version_info', verinfo)
        self.set_ext('header_size', len(verinfo))
        # save Device info
        self.set_ext('device_name', device_name)
        self.set_ext('payload_sections', payload_sections)

        # Save File info
        if file_info_names:
            file_dict = dict(zip(file_info_names, file_info_datas))
            file_ver = file_dict['VERSION']
        else:
            # V1 version
            file_ver = 1

        v.msg(v.INFO, '[V{} Version Header]'.format(file_ver))
        self.set_ext('file_version', file_ver)

        header_info = self.build_info_block(verinfo, version_info_datas)
        if file_ver > 1:
            ext = self.extract_info_block(header_info, file_ver)
            if len(ext):
                self.set_ext('header_ext_data', ext)
        
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

    def _full_checksum_name(self):
        """Resolve the checksum field name, including a device suffix when needed.

        Input:
            None.
        Output:
            Checksum field name used by the current xcfg version.
        """
        checksum_name = self.INFO_BLOCK_NAME[self.CHECKSUM]
        device_name = self.get_ext('device_name')
        if device_name:
            checksum_name = checksum_name + '_' +  device_name
        
        return checksum_name

    def payload_sections(self, default=None):
        """Return parsed payload-section metadata.

        Input:
            default: Fallback value when no payload sections were parsed.
        Output:
            List of payload dictionaries or the provided default.
        """
        return self.get_ext('payload_sections', default)

    def output_version(self, output):
        """Resolve the effective xcfg output version from CLI intent and input version.

        Input:
            output: CLI output selector or None.
        Output:
            Effective xcfg output version integer.
        """
        file_ver = self.get_ext('file_version', 1)

        if output is None:
            return 1 if file_ver <= 2 else file_ver

        if output <= 1:
            return 1

        return 1 if file_ver <= 2 else file_ver

    def _rebuild_checksum_header(self, lines, calculated_crc):
        """Build the replacement checksum line within the version header block.

        Input:
            lines: Slice of version-header lines.
            calculated_crc: Newly calculated config CRC.
        Output:
            Tuple of (line_index, replacement_line) or (None, None).
        """

        key = self._full_checksum_name()
        excluded = self.INFO_BLOCK_NAME[self.INFO_BLOCK_CHECKSUM].split('_')[0]

        for idx, line in enumerate(lines):
            line = self.decode(line)
            if line.isspace():
                continue

            tag = self.check_header(line)[0]
            if tag:
                break

            raw = line.strip().split('=')
            if len(raw) == 2:
                if key == raw[0].strip() and excluded not in line:
                    data = '{:s}=0x{:06X}\r\n'.format(key, calculated_crc)
                    return idx, data

        return None, None

    def replace_checksum(self, content):
        """Replace the stored config checksum when it differs from the calculated CRC.

        Input:
            content: Full xcfg file content as a list of lines.
        Output:
            Updated content list or None when no replacement is needed.
        """

        calculated_crc = self.calculated_crc()
        config_crc = self.config_crc()

        if calculated_crc == config_crc:
            v.msg(v.INFO, 'Config CRC matched ({:06X}), Skip save xcfg file'.format(config_crc))
            return None
        else:
            v.msg(v.WARN, 'Use Calculated CRC ({:06X}) overwrite File CRC({:06X})'.format(calculated_crc, config_crc))

            for i, line in enumerate(content):
                tag, result = self.check_header(line)
                if result:
                    if tag is self.T_COMMENTS:
                        pass
                    elif tag is self.T_FILE_INFO_HEADER:
                        pass
                    elif tag is self.T_VERSION_INFO_HEADER:
                        st = i + 1
                        end = st + self.get_ext('header_size')
                        idx, data = self._rebuild_checksum_header(content[st:end], calculated_crc)
                        if idx is not None:
                            content[st + idx] = data # if sys.version_info.major == 3 else self.encode(data)
                            v.msg(v.DEBUG2, content[st:end])
                        else:
                            v.msg(v.ERR, 'Overwrite CRC failed, {:s} not found in header:'.format(self.INFO_BLOCK_NAME[self.CHECKSUM]))
                            v.msg(v.ERR, content[st:end])
                        break
                    elif tag is self.T_APPLICATION_INFO_HEADER:
                        break
                    elif tag is self.T_OBJECT_DATA:
                        break
            return content

    def convert_output_format(self, content, ver):
        """Convert higher-version xcfg text into the low-version compatible format.

        Input:
            content: Full xcfg file content.
            ver: Target output version.
        Output:
            New list of xcfg lines after format conversion.

        Key steps:
            1. Drop unsupported low-version sections like FILE_INFO_HEADER and DEVICE blocks.
            2. Rename device-specific checksum fields when converting to V1.
            3. Preserve higher-version fields only when the target format allows them.
        """

        v.msg(v.INFO, 'Convert config from V{} version to V1 version:'.format(ver))
        content_new = []
        tag = None
        for line in content:
            drop = False
            t, hit_tag = self.check_header(line)
            if hit_tag:
                tag = t

            if tag is self.T_VERSION_INFO_HEADER:
                if not hit_tag:
                    if not line.isspace():
                        raw = line.strip().split('=')
                        if len(raw) == 2:
                            name = raw[0]
                            if name not in self.INFO_BLOCK_NAME:
                                if ver < 4:
                                    if name == self._full_checksum_name():
                                        # cover the checksum name to common name in version less than 4
                                        line = "{:s}={:s}\r\n".format(self.INFO_BLOCK_NAME[self.CHECKSUM], raw[1])
                                    else:
                                        # skip all extra fields in version less than 4
                                        v.msg(v.INFO, "drop {:s}".format(name))
                                        drop = True
                                else:
                                    # keep all fields in version 4
                                    pass
                                
            elif tag is self.T_FILE_INFO_HEADER:
                v.msg(v.INFO, "drop {:s}".format(line))
                drop = True
            elif tag is self.T_DEVICE:
                v.msg(v.INFO, "drop {:s}".format(line))
                drop = True
            else:
                pass

            if not drop:
                content_new.append(line)
        
        return content_new

    def save(self, output, path=None):
        """Save a rebuilt xcfg file using the resolved checksum and output-version policy.

        Input:
            output: CLI output selector or None.
            path: Optional base path used to derive the output directory/name.
        Output:
            None. Writes a rebuilt xcfg file when content needs to change.

        Key steps:
            1. Replace the checksum when needed.
            2. Optionally convert higher-version content to V1-compatible format.
            3. Build a timestamped relative output filename and write the file.
        """

        if not self.xcfg_content:
            return

        if not path:
            path = self.get_path()

        generate = False
        # Replace the checksum if mismatch
        content = self.replace_checksum(self.xcfg_content)
        if content:
            generate = True
        else:
             content = self.xcfg_content

        # Convert the output version format
        file_ver = self.get_ext('file_version')
        target_ver = self.output_version(output)

        if target_ver == 1 and file_ver > 1: # Output assigned to version 1
            content = self.convert_output_format(content, target_ver)
            if content:
                generate = True
                file_ver = target_ver
        else:
            file_ver = target_ver

        if not generate:
            return

        dir = os.path.dirname(path)
        name = os.path.basename(path)

        if not dir:
            dir = os.path.dirname(self.get_path())

        if not dir:
            dir = os.getcwd()

        if not name:
            name = os.path.basename(self.get_path())

        raw = name.rsplit('.', 1)
        main = raw[0]
        ext = 'xcfg'

        now = datetime.datetime.now()
        basename = '.'.join([main, 'rebuild(v{:d})_at'.format(file_ver), now.strftime('%Y%m%d_%H%M%S'), 'crc_0x{:06X}'.format(self.calculated_crc()), ext])
        filename = os.path.join(dir, basename)
        v.msg(v.CONST, 'Save xcfg file to: {:s}'.format(filename))
        if os.path.exists(filename):
            os.remove(filename)

        with open(filename, 'wb') as outfile:
            for line in content:
                outfile.write(self.encode(line))
            #outfile.write(''.join(map(byte, content))
            #outfile.write('\n')
            outfile.close()

    def objects_num(self, default=0):
        """Estimate the raw object-count field used in raw header export.

        Input:
            default: Fallback count when no object table exists.
        Output:
            Integer object count used by raw export helpers.
        """

        num = default
        title = self.get('object_title')
        if title is not None:
            objects = set(title['object'])
            num = len(objects) + 2  #T9/T100 T6
            if 100 in objects:
                num += 1    #T44

        return num

    def info_crc(self, default=None):
        """Return the info-block checksum stored in the parsed header.

        Input:
            default: Fallback value when unavailable.
        Output:
            Info-block checksum integer or the provided default.
        """
        header = self.get('header_info')
        if header is not None and len(header) >= self.INFO_BLOCK_CHECKSUM:
            return header.loc[self.INFO_BLOCK_NAME[self.INFO_BLOCK_CHECKSUM]]

        return default

    def config_crc(self, default=None):
        """Return the config checksum stored in the parsed header.

        Input:
            default: Fallback value when unavailable.
        Output:
            Config checksum integer or the provided default.
        """
        header = self.get('header_info')
        if header is not None and len(header) >= self.CHECKSUM:
            return header.loc[self.INFO_BLOCK_NAME[self.CHECKSUM]]

        return default

    def calculated_crc(self, default=None):
        """Return the calculated CRC cached during parsing.

        Input:
            default: Fallback value when unavailable.
        Output:
            Calculated CRC integer or the provided default.
        """
        return self.get_ext('calculated_crc', default)

class XcfgCalculateCRC(object):
    """CRC24 calculator for config data extracted from XCFG/RAW sources."""

    def __init__(self, xcfg):
        """Store the parser instance that supplies object/header data."""
        self.xcfg = xcfg

    def load(self, path):
        """Load an xcfg file through the bound parser.

        Input:
            path: Path to an xcfg file.
        Output:
            None. Delegates loading to the bound parser instance.
        """
        self.xcfg.load(path)

    @classmethod
    def __crc24(cls, crc, byte0, byte1):
        """Advance the 24-bit CRC state by one 16-bit little-endian word.

        Input:
            crc: Current CRC accumulator.
            byte0: Low byte of the next data word.
            byte1: High byte of the next data word.
        Output:
            Updated 24-bit CRC accumulator.
        """

        crcpoly = 0x80001B

        data_word = (byte1 << 8) | byte0
        result = ((crc << 1) ^ data_word)

        if result & 0x1000000:
            result ^= crcpoly

        return result

    @classmethod
    def calculate_crc(cls, data, start_off=None, end_off=None):
        """Calculate the CRC24 for a slice of byte data.

        Input:
            data: Byte list.
            start_off: Optional start offset.
            end_off: Optional exclusive end offset.
        Output:
            24-bit CRC integer for the selected data window.
        """

        ptr = data[start_off:end_off]

        v.msg(v.DEBUG2, 'calcualte crc: st={} end={} len={}'.format(start_off, end_off, len(ptr)))

        if not len(ptr):
            return 0

        if len(ptr) & 0x1:
            ptr.append(0)

        crc = 0
        for i in range(len(ptr) // 2):
            crc = cls.__crc24(crc, ptr[i * 2], ptr[i * 2 + 1])

            # Mask to 24-bit
        crc &= 0x00FFFFFF

        return crc

    def calculate(self):
        """Calculate the config CRC using the parser's object table and byte stream.

        Input:
            None.
        Output:
            Calculated CRC integer or None when required blocks are missing.

        Key steps:
            1. Find the CRC start object using the T14/T71/T7 priority rule.
            2. Calculate CRC across object_data from that offset onward.
            3. Compare the result with the stored header CRC for reporting.
        """
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
        st_regs = {}
        st_order = {14 : 1, 71 : 2, 7 : 3}  #priority: T14 > T71 > T7
        for idx in title.index:
            t_info = title.loc[idx]
            if t_info['object'] in st_order.keys():
                if t_info['instance'] == 0: #only store the 'start' at instance 0
                    st_regs[t_info['object']] = t_info

        if not len(st_regs):
            v.msg(v.ERR, 'Missed {} object, not CRC calculated', st_order.keys())
            return

        st = sorted(st_regs, key=lambda x: st_order[x])[0]  # get first sorted object
        start = st_regs[st]['offset']   #calculate from offset of raw data
        v.msg(v.CONST, "Start address is T{}, addr {} offset {}".format(st, st_regs[st]['address'], start))
        calculated_crc = self.calculate_crc(data, start)
        matched = calculated_crc == header.loc[self.xcfg.INFO_BLOCK_NAME[self.xcfg.CHECKSUM]]

        v.msg(v.CONST, 'CRC: calculate={:6X}, cfg={:6X} {:s}'.
              format(calculated_crc,
                     header.loc[self.xcfg.INFO_BLOCK_NAME[self.xcfg.CHECKSUM]],
                     '(matched)' if matched else '(mismatch) X X X'))

        self.calculated_crc = calculated_crc

        return calculated_crc


class XcfgBuildRawFile(object):
    """Convert parsed xcfg content into raw-file text output."""

    PAYLOAD_OBJECT = 68
    PAYLOAD_INSTANCE = 0x800D

    LOOKUP_DB_TABLE = [
        XcfgConfigParser.INFO_BLOCK_NAME[XcfgConfigParser.FAMILY_ID],
        XcfgConfigParser.INFO_BLOCK_NAME[XcfgConfigParser.VARIANT],
        XcfgConfigParser.INFO_BLOCK_NAME[XcfgConfigParser.VERSION],
        XcfgConfigParser.INFO_BLOCK_NAME[XcfgConfigParser.BUILD],
        XcfgConfigParser.INFO_BLOCK_NAME[XcfgConfigParser.INFO_BLOCK_CHECKSUM]]

    def __init__(self, xcfg):
        """Store the parsed xcfg source and initialize optional DB state."""
        self.xcfg = xcfg
        self.db = None

    def load_db(self, db):
        """Load an info-block lookup database used to fill raw header metadata.

        Input:
            db: pandas.DataFrame with raw header columns.
        Output:
            None. Stores a validated copy of the database.
        """

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
        """Find a matching DB row for the current header signature.

        Input:
            header: Parsed xcfg header series.
        Output:
            Matching pandas row or None when no row matches.
        """

        if self.db is None:
            return

        cond = []
        for item in self.LOOKUP_DB_TABLE:
            cond.append('{:s}=={:d}'.format(item, header.loc[item]))

        words = ' & '.join(cond)
        v.msg(v.DEBUG, words)
        result = self.db.query(words)
        if len(result):
            return result.iloc[0]
        else:
            return None

    def get_extra_info(self, header):
        """Resolve MATRIX_X/Y and object count for raw-header generation.

        Input:
            header: Parsed xcfg header series.
        Output:
            Tuple of (matrix_x, matrix_y, objects_num).

        Key steps:
            1. Prefer version-header extension data already present in the xcfg.
            2. Fall back to the scanned database when available.
            3. Prompt the user only when metadata still cannot be resolved.
        """

        # from header info ext first
        info_ext = self.xcfg.get_ext('header_ext_data')
        if info_ext and len(info_ext) >= 3:  # MATRIX_X, MATRIX_Y, OBJECTS_NUM
            return tuple(info_ext[:3])

        result = self.lookup_db(header)
        if result is not None:
            #print(result.apply(lambda x: '{:02X}'.format(x)))
            ext = result.loc[RawConfigParser.RAW_INFO_BLOCK_NAME[RawConfigParser.MATRIX_X]], result.loc[RawConfigParser.RAW_INFO_BLOCK_NAME[RawConfigParser.MATRIX_Y]], result.loc[RawConfigParser.RAW_INFO_BLOCK_NAME[RawConfigParser.OBJECTS_NUM]]
        else:
            ext = [0, 0]
            v.msg(v.WARN, header.apply(lambda x: '{:02X}'.format(x)))
            v.msg(v.WARN, 'Please input the MATRIX_X/Y, format is <x, y>: ')
            v.msg(v.WARN, '## e.g. For \'336T\', input: 24,14')
            try:
                raw = input('input x,y: ').split(',')
                if len(raw) == 2:
                    ext = list(map(int, raw))
            except:
                v.msg(v.ERR, 'Input value error')

            if not all(ext):
                raise ValueError('Invalide Maxtrix value: {:d},{:d}'.format(ext[0], ext[1]))

            num = self.xcfg.objects_num()
            v.msg(v.WARN, 'Please confirm object numbers: ({:d} default)'.format(num))
            try:
                raw = input('input object numbers: ')
                if len(raw) == 1:
                    num = int(raw)
            except:
                v.msg(v.ERR, 'Input error, Use default ({:d})', num)
            finally:
                ext.append(num)

        return tuple(ext)

    def get_no_devices(self, default=1):
        """Return the parsed device count used by V4 raw output.

        Input:
            default: Fallback device count.
        Output:
            Integer number of devices.
        """
        info_ext = self.xcfg.get_ext('header_ext_data')
        if info_ext and len(info_ext) >= 4:
            return info_ext[3]

        return default

    def output_version(self, output_ver):
        """Resolve the raw output version from CLI intent and input xcfg version.

        Input:
            output_ver: CLI selector or None.
        Output:
            Effective raw version constant.
        """
        file_ver = self.xcfg.get_ext('file_version', 1)

        if output_ver is None:
            return 1

        if output_ver <= 1:
            return 1

        if file_ver >= RawConfigParser.RAW_VERSION_4:
            return RawConfigParser.RAW_VERSION_4

        if file_ver >= RawConfigParser.RAW_VERSION_3:
            return RawConfigParser.RAW_VERSION_3

        return 1

    def payload_lines(self):
        """Convert parsed payload sections into dedicated raw-record lines.

        Input:
            None.
        Output:
            List of raw text lines representing payload records.

        Key steps:
            1. Read parsed payload bytes from the xcfg parser.
            2. Append a separator byte and big-endian payload checksum bytes.
            3. Emit the dedicated T68 raw pseudo-record format.
        """
        sections = self.xcfg.payload_sections([])
        lines = []
        for section in sections:
            payload = list(section.get('data', []))
            if not payload:
                continue

            checksum = int(section.get('checksum', 0))
            payload.extend([
                0,
                (checksum >> 16) & 0xff,
                (checksum >> 8) & 0xff,
                checksum & 0xff,
            ])

            trunk = [
                '{:04X}'.format(self.PAYLOAD_OBJECT),
                '{:04X}'.format(self.PAYLOAD_INSTANCE),
                '{:04X}'.format(len(payload)),
                ' '.join('{:02X}'.format(x) for x in payload),
            ]
            lines.append(' '.join(trunk))

        return lines

    def rebuild_raw_header_block(self, data, matrix_x, matrix_y, object_num):
        """Build the compact raw-header payload line.

        Input:
            data: Parsed xcfg header series.
            matrix_x: Resolved X matrix size.
            matrix_y: Resolved Y matrix size.
            object_num: Resolved raw object count.
        Output:
            pandas.Series representing the raw header block.
        """

        data_new = list(data[:RawConfigParser.BUILD + 1])
        data_new.extend([matrix_x, matrix_y, object_num])

        info_block = pd.Series(data=data_new, index=RawConfigParser.RAW_INFO_BLOCK_NAME[:len(data_new)])

        return info_block

    def rebuild_raw_data(self, output_ver=None):
        """Build the full raw file content from the parsed xcfg.

        Input:
            output_ver: CLI selector or None.
        Output:
            None. Stores generated text lines into self.raw_content.

        Key steps:
            1. Resolve the effective raw output version.
            2. Emit version-specific raw headers and metadata lines.
            3. Append object records and optional payload records.
        """

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
        raw_ver = self.output_version(output_ver)

        #RAW_HEADER
        if raw_ver >= RawConfigParser.RAW_VERSION_4:
            lines.append(RawConfigParser.RAW_FILE_HEADER_MAGIC_WORD_V4)
        elif raw_ver >= RawConfigParser.RAW_VERSION_3:
            lines.append(RawConfigParser.RAW_FILE_HEADER_MAGIC_WORD_V3)
        else:
            lines.append(RawConfigParser.RAW_FILE_HEADER_MAGIC_WORD)

        if raw_ver >= RawConfigParser.RAW_VERSION_3:
            lines.append('ENCRYPTION 0')
            lines.append('MAX_ENCRYPTION_BLOCKS 0')

        if raw_ver >= RawConfigParser.RAW_VERSION_4:
            lines.append('NO_DEVICES {:d}'.format(self.get_no_devices()))
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

        if raw_ver >= RawConfigParser.RAW_VERSION_4:
            lines.append('[DEVICE_0]')
        #RAW_CONFIG_DATA

        payload_lines = self.payload_lines()
        for idx in title.index:
            info = title.loc[idx]

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

        # Keep payload-type T68 data at the end of RAW output.
        if payload_lines:
            lines.extend(payload_lines)

        v.msg(v.INFO, '\n'.join(lines))
        self.raw_content = lines

    def save_raw_file(self, output, path=None):
        """Write the generated raw content to a timestamped output file.

        Input:
            output: CLI selector or None.
            path: Optional base path used to derive output directory/name.
        Output:
            None. Writes a raw text file when raw_content is available.
        """
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

        raw = name.rsplit('.', 1)
        main = raw[0]
        ext = 'raw'
        raw_ver = self.output_version(output)

        now = datetime.datetime.now()
        crc = xcfg.calculated_crc(0)
        basename = '.'.join([main, 'rebuild(v{:d})_at'.format(raw_ver), now.strftime('%Y%m%d_%H%M%S'), 'crc_0x{:06X}'.format(crc), ext])
        filename = os.path.join(dir, basename)
        if os.path.exists(filename):
            os.remove(filename)

        with open(filename, 'w') as outfile:
            outfile.write('\n'.join(self.raw_content))
            outfile.write('\n')
            outfile.close()
            v.msg(v.CONST, 'Save raw file to: {:s}'.format(filename))

class RawConfigScanner(RawConfigParser):
    """Scan directories of raw files to build and maintain the header database."""

    PARAM = {'db_file': 'db_header.csv',
                'max_scan_files': 5000,
                'db_col': RawConfigParser.RAW_INFO_BLOCK_NAME[:RawConfigParser.CHECKSUM]}

    def __init__(self):
        """Initialize the scanner, parser helper, and in-memory database."""
        super(RawConfigScanner, self).__init__()
        self.parser = RawConfigParser(method=RawConfigParser.PARSE_HEADER)
        self.db = pd.DataFrame(columns=self.PARAM['db_col'])
        self.db_file = os.path.join(os.getcwd(), self.PARAM['db_file'])
        self.db_new = False

    def load(self, path=None):
        """Load the CSV header database from disk.

        Input:
            path: Optional override path to the CSV database file.
        Output:
            pandas.DataFrame or None when loading fails.
        """
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
        """Persist the updated header database when new entries were added.

        Input:
            None.
        Output:
            None. Writes the CSV file only when db_new is True.
        """

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
            finally:
                v.msg(v.INFO, self.db.applymap(lambda x: '{:02X}'.format(x)))

        self.db_new = False

    def __search_header_in_dirs(self, path, limited=0):
        """Search a directory tree for raw files and extract header blocks.

        Input:
            path: Directory path to scan.
            limited: Unused placeholder for future scan limiting.
        Output:
            Tuple of (header_block_list, file_path_list).
        """

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
        """Ask the user how to resolve a duplicate header signature conflict.

        Input:
            db_header: Existing database header row.
            header: Newly discovered header row.
            extra: Context string, usually the source file path.
        Output:
            Selected header row or None when both entries should be discarded.
        """
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
        """Insert a new header row unless a conflicting duplicate must be resolved.

        Input:
            db_list: Current database rows as a mutable list.
            header: Candidate header row.
            extra: Optional source-path context.
        Output:
            Inserted/replaced header row, or None when nothing changes.
        """

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
        """Scan a file or directory for raw headers and merge them into the DB.

        Input:
            path: File or directory to scan.
        Output:
            Updated pandas.DataFrame database.

        Key steps:
            1. Normalize file input into a scan directory.
            2. Parse headers from all discovered raw files.
            3. Merge non-duplicate entries and mark the DB dirty when changed.
        """

        db_list = self.db.values.tolist()
        new_list = []
        if os.path.exists(path):
            if os.path.isfile(path):
                path = os.path.dirname(path)
            v.msg(v.ERR, 'search path: {:s}'.format(path))
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


if __name__ == "__main__":
    value = "A2 17 10 AA 20 34 22 25 D6 00 81 00 00 2C 58 01 00 00 00 05 59 01 08 00 00 06 62 01 05 00 01 44 68 01 48 00 01 26 B1 01 3F 00 00 47 F1 01 A7 00 00 07 99 02".split()
    data = [int(v, 16) for v in value[:-3]]
    print('Debug XcfgCalculateCRC.calculate_crc():')
    print(len(data))
    print("Info block len:", data[6] * 6 + 7 + 3)
    crc32 = XcfgCalculateCRC.calculate_crc(data, start_off=None, end_off=None)
    print(hex(crc32))