
usage: xparse [-h] [--version] [-f [XCFG]] [-s [DIR]] [-db [DATABASE]] [-v {0,1,2,3,4}]<br>

Tools for parsing maxTouch config and calculating config crc<br>
------------------

###		
	optional arguments:<br>
	-h, --help				show this help message and exit<br>
	--version				show version<br>
	-f [XCFG], --filename [XCFG]<br>
						where the 'XCFG' file will be load (default: )<br>
	-s [DIR], --scan [DIR]<br>
						Path will be scanned to build chip Info Block database(default: )<br>
	-db [DATABASE], --database [DATABASE]<br>
						load chip Info Block database (default: db_header.csv)<br>
	-v {0,1,2,3,4}, --verbose {0,1,2,3,4}<br>
						set debug verbose level[0-5] (default: 3)<br>


e.g.
	run in python command line:<br>
	
	
	python runstat.py -f d:/temp/temp/1.xcfg -s D:\Document\trunk\customers2
	output:
	 Namespace(database='db_header.csv', filename='d:/temp/temp/1.xcfg', scan='D:\\Document\\trunk\\customers2', verbose=1)
	('Save db to file: D:\\Users\\pitter.liao\\PycharmProjects\\config_crc\\db_header.csv',)
	('CRC: calculate=5C4754, cfg=5C4750 (mismatch) X X X',)
	('Use Calculated CRC (5C4754) overwrite File CRC(5C4750)',)
	('Save xcfg file to: d:/temp/temp\\1.20170526_221640.rebuild.xcfg',)
	('Save raw file to: d:/temp/temp\\1.20170526_221640.rebuild.raw',)
