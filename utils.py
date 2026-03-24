from config_parser import XcfgCalculateCRC
import os

class Calculate_CRC(object):
    """Utility class for calculating CRC values from plain hexadecimal text files."""

    def __init__(self, sep=None):
        """Store the field separator used to split raw hexadecimal input lines.

        Input:
            sep: Optional delimiter passed to str.split when parsing text rows.
        Output:
            None. Initializes the cached CRC result to None.
        """
        self.crc32 = None
        self.sep = sep

    def load_file(self, path):
        """Read a text file, convert hex bytes, and calculate CRC variations.

        Input:
            path: Path to a text file containing hexadecimal byte values.
        Output:
            None. Stores the last calculated CRC in self.crc32 and prints details.

        Key steps:
            1. Read all rows and split them into hexadecimal byte tokens.
            2. Flatten the parsed byte stream into a single list.
            3. Calculate CRC for the full stream and for the stream without the last 3 bytes.
        """
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
        """Return the last CRC value produced by load_file.

        Input:
            None.
        Output:
            The cached CRC integer or None if no file has been processed.
        """
        return self.crc32