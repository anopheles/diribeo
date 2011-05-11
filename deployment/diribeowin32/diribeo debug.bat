@echo off
SET PATH=%CD%\Python26\Lib\site-packages\PyQt4\bin
SET PYTHONPATH=%CD%\Python26
cd diribeo
..\Python26\python diribeo.py
PAUSE