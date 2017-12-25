from config_parser import XcfgCalculateCRC
import os

class Calculate_CRC(object):
    def __init__(self, sep=None):
        self.crc32 = None
        self.sep = sep

    def load_file(self, path):
        if os.path.exists(path):
            with open(path) as fp:
                data = []
                for line in list(fp):
                    bins = line.split(self.sep)
                    val = [int(c, 16) for c in bins]
                    data.extend(val)

                print("File data length:", len(data))
                print("Get info block len:", data[6] * 6 + 7 + 3)
                crc = XcfgCalculateCRC.calculate_crc(data, start_off=None, end_off=None)
                print('CRC32(Full bytes):', hex(crc))
                crc = XcfgCalculateCRC.calculate_crc(data, start_off=None, end_off=len(data) - 3)
                print('CRC32(Split last 3 bytes):', hex(crc))
                self.crc32 =crc

    def get_crc32(self):
        return self.crc32