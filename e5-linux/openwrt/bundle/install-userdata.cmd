@echo off
rem Install into a sized image on userdata, without an SD card.
call "%~dp0flash.cmd" --data %*
