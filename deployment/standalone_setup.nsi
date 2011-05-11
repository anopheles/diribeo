!define py2exeOutputDir 'diribeo win32'
!define exe             'diribeo.exe'
!define icon            'favicon.ico'
!define compressor      'lzma'  ;one of 'zlib', 'bzip2', 'lzma'
!define onlyOneInstance

; - - - - do not edit below this line, normaly - - - -
!ifdef compressor
    SetCompressor ${compressor}
!else
    SetCompress Off
!endif
Name ${exe}
OutFile ${exe}
SilentInstall silent
!ifdef icon
    Icon ${icon}
!endif

; - - - - Allow only one installer instance - - - - 
!ifdef onlyOneInstance
Function .onInit
 System::Call "kernel32::CreateMutexA(i 0, i 0, t '$(^Name)') i .r0 ?e"
 Pop $0
 StrCmp $0 0 launch
  Abort
 launch:
FunctionEnd
!endif
; - - - - Allow only one installer instance - - - - 

Section
    
    ; Get directory from which the exe was called
    System::Call "kernel32::GetCurrentDirectory(i ${NSIS_MAX_STRLEN}, t .r0)"
    
    ; Unzip into pluginsdir
    InitPluginsDir
    SetOutPath '$0\Diribeo'
    File /r '${py2exeOutputDir}\*.*'
    
    ; Set working dir and execute, passing through commandline params
    SetOutPath '$0\Diribeo'
    ExecWait '"$0\Diribeo\diribeo.bat" $R0' $R2
    SetErrorLevel $R2
 
SectionEnd