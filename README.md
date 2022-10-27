
Enviroment:

Install Python:
https://www.python.org/downloads/

After installation, run python in command line:

python -m pip install pandas


usage: xparse [-h] [--version] [-f [XCFG]] [-s [DIR]] [-db [DATABASE]] [-v {0,1,2,3,4}]<br>

Tools for parsing maxTouch config and calculating config crc<br>
------------------

###		
Namespace(filename='', raw=False, sep=None, scan='', database='db_header.csv', verbose=1, output=1)
usage: Maxtouch Config calculator [-h] [--version] [-f [XCFG|TXT]] [-r] [-sep [SEP]] [-s [DIR]] [-db [DATABASE]]
                                  [-v {0,1,2,3,4}] [-o {1,3}]

Tools for parsing maxTouch config and calculating config crc

options:

	-h, --help            show this help message and exit
	--version             show version
	-f [XCFG|TXT], --filename [XCFG|TXT]
                        where the 'XCFG|TXT' file will be load (default: )
	-r, --raw             whether save out a 'RAW' file (default: False)
	-sep [SEP], --sep [SEP]
                        Delimiters for 'Raw Block' split() to data (default: None)
	-s [DIR], --scan [DIR]
                        Path will be scanned to build chip Info Block database (default: )
	-db [DATABASE], --database [DATABASE]
                        load chip Info Block database (default: db_header.csv)
	-v {0,1,2,3,4}, --verbose {0,1,2,3,4}
                        set debug verbose level[0-5] (default: 1)
	-o {1,3}, --output {1,3}
                        set the output config file version (default: 1)
e.g.
	run in python command line:<br>
	
python runstat.py -f test.xcfg --raw

Namespace(filename='test.xcfg', raw=True, sep=None, scan='', database='db_header.csv', verbose=1, output=1)
("Found Non-Number value at line: `PRODUCT_ID=TBD`, Error = `invalid literal for int() with base 0: 'TBD'`. Set Value to 0",)

('Start address is T14, addr 415 offset 194',)

('CRC: calculate=B277E4, cfg=BA8CF0 (mismatch) X X X',)

('Use Calculated CRC (B277E4) overwrite File CRC(BA8CF0)',)

('Save xcfg file to: D:\\Users\\a41450\\PycharmProjects\\config_crc\\test.rebuild(v1)_at.20221027_115717.crc_0xB277E4.xcfg',)

('Save raw file to: D:\\Users\\a41450\\PycharmProjects\\config_crc\\test.rebuild(v1)_at.20221027_115717.crc_0xB277E4.raw',)

Note：
For v1 version config, there is not X/Ysize information, need scan the director first with '-s'

