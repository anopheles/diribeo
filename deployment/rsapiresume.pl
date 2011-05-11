#!/usr/bin/perl

my $DESC = qq|RapidShare AG Open Source Perl Uploader.
For non-commercial use only. All rights reserved. USE AT YOUR OWN RISK!

Version 2.4.1 (22th Apr 2011)

Features:
 - Uploads files and folders to your premium zone.
 - Supports MD5 check after uploads to check if the upload worked.
 - Supports upload resume to continue aborted uploads.
 - Supports RealFolders.
 - Supports update and trash modes to update remote files without changing file IDs.

Syntax: $0 <file/folder> <login> <password> [updatemode] [trashmode]

This tool uploads a file or a folder structure to RapidShare. If you want to sync a
local folder with a remote folder, you should use updatemode=1 to avoid re-uploading
already existing files. Notice that this overwrites existing files!
(Actually this is the only reason why this is not the default behaviour.)

updatemode:
0 = Traditional uploading. No duplicate checking. (Default)
1 = The lowest file ID duplicate will be overwritten if MD5 differs. Other duplicates
    will be handled using the trash flag.

thrashmode:
0 = Secondary duplicates will just be ignored. (Default)
1 = Secondary duplicates will be moved to the trash RealFolder ID 999
2 = Secondary duplicates will be DELETED! (not undoable)
|;



use strict;
use warnings;
use Digest::MD5("md5_hex");
use Fcntl;
use IO::Socket;
use LWP::Simple;

my ($CHUNKSIZE, $FILE, $LOGIN, $PASSWORD, $UPDATEMODE, %ESCAPES, $TRASHMODE, %PARENTANDNAME_REALFOLDER);

$/ = undef;
$| = 1;
$SIG{PIPE} = $SIG{HUP} = 'IGNORE';
$CHUNKSIZE = 1_000_000;
$FILE = $ARGV[0] || "";
$LOGIN = $ARGV[1] || "";
$PASSWORD = $ARGV[2] || "";
$UPDATEMODE = $ARGV[3] || 0;
$TRASHMODE = $ARGV[4] || 0;

unless ($PASSWORD) { die $DESC . "\n" }
unless (-e $FILE) { die "File not found.\n" }

if (-d $FILE) {
  print "Counting all folders and files in $FILE...\n";

  my ($numfiles, $numfolders, $numbytes) = &countfiles($FILE);

  printf("You want to upload $numfiles files and $numfolders sub folders having $numbytes bytes (%.2f MB)\n", $numbytes / 1000000);

  if ($numfiles > 1000) { die "More than 1000 files? You should not do that...\n" }
  if ($numfolders > 100) { die "More than 100 folders? You should not do that...\n" }
  if ($numbytes > 100_000_000_000) { die "More than 100 Gigabytes? You should not do that...\n" }

  &listrealfolders($LOGIN, $PASSWORD);
  &uploadfolder($FILE, $LOGIN, $PASSWORD);
} else {
  &uploadfile($FILE, $LOGIN, $PASSWORD);
}

print "All done.\n";
exit;





sub countfiles {
  my $dir = shift || die;

  my (@entries, $filename, $numfiles, $numfolders, $numbytes, $subnumfiles, $subnumfolders, $subnumbytes, $filesize);

  unless (opendir(DIR, $dir)) { die "Unable to open dir '$dir': $!\n" }
  @entries = readdir(DIR);
  closedir(DIR);

  foreach $filename (@entries) {
    if ($filename eq "." or $filename eq ".." or $filename =~ /\.uploaddata$/) { next }

    if (-d "$dir/$filename") {
      ($subnumfiles, $subnumfolders, $subnumbytes) = &countfiles("$dir/$filename");
      $numfiles += $subnumfiles;
      $numfolders++;
      $numbytes += $subnumbytes;
    } else {
      $numfiles++;
      $filesize = -s "$dir/$filename";
      unless ($filesize) { die "0 byte file $dir/$filename not supported.\n" }
      if ($filesize > 4_294_000_000) { die "File $dir/$filename having more than 4_294_000_000 bytes ($filesize) not supported.\n" }
      $numbytes += $filesize;
    }
  }

  return ($numfiles || 0, $numfolders || 0, $numbytes || 0);
}





sub uploadfolder {
  my $folder = shift || die;
  my $login = shift || "";
  my $password = shift || "";
  my $parent = shift || 0;

  my ($shortfolder, $realfolder, $mode, $htmllogin, $htmlpassword, $htmlshortfolder, @entries, $filename);

  ($shortfolder) = $folder =~ /([^\/]+)\z/;
  $realfolder = $PARENTANDNAME_REALFOLDER{"$parent,$shortfolder"} || 0;
  $mode = "existed";

  unless ($realfolder) {
    $htmllogin = &htmlencode($login);
    $htmlpassword = &htmlencode($password);
    $htmlshortfolder = &htmlencode($shortfolder);
    $realfolder = get("http://api.rapidshare.com/cgi-bin/rsapi.cgi?sub=addrealfolder_v1&login=$htmllogin&password=$htmlpassword&name=$htmlshortfolder&parent=$parent") || "";
    if (not $realfolder or $realfolder =~ /^ERROR: /) { die "API Error occured: $realfolder\n" }
    $mode = "created";
    unless ($realfolder =~ /^\d+$/) { die "Error adding RealFolder: $realfolder\n" }
  }

  print "Folder '$shortfolder' resolved to ID $realfolder ($mode)\n";

  unless (opendir(DIR, $folder)) { die "Unable to open dir '$folder': $!\n" }
  @entries = readdir(DIR);
  closedir(DIR);

  foreach $filename (@entries) {
    if ($filename eq "." or $filename eq ".." or $filename =~ /\.uploaddata$/) { next }
    if (-d "$folder/$filename") { &uploadfolder("$folder/$filename", $login, $password, $realfolder) } else { &uploadfile("$folder/$filename", $login, $password, $realfolder) }
  }

  return "";
}





sub listrealfolders {
  my $login = shift || die;
  my $password = shift || die;

  my ($htmllogin, $htmlpassword, $result, $realfolder, $parent, $name);

  $htmllogin = &htmlencode($login);
  $htmlpassword = &htmlencode($password);

  $result = get("http://api.rapidshare.com/cgi-bin/rsapi.cgi?sub=listrealfolders_v1&login=$htmllogin&password=$htmlpassword") || "";
  if (not $result or $result =~ /^ERROR: /) { die "API Error occured: $result\n" }

  foreach (split(/\n/, $result)) {
    ($realfolder, $parent, $name) = split(/,/, $_, 3);
    $PARENTANDNAME_REALFOLDER{"$parent,$name"} = $realfolder;
  }

  return "";
}





sub finddupes {
  my $login = shift || die;
  my $password = shift || die;
  my $realfolder = shift || 0;
  my $filename = shift || "";

  my ($htmllogin, $htmlpassword, $htmlfilename, $result, $fileid, $size, $killcode, $serverid, $md5hex, $dupefileids);

  $htmllogin = &htmlencode($login);
  $htmlpassword = &htmlencode($password);
  $htmlfilename = &htmlencode($filename);
  $result = get("http://api.rapidshare.com/cgi-bin/rsapi.cgi?sub=listfiles_v1&login=$htmllogin&password=$htmlpassword&realfolder=$realfolder&filename=$htmlfilename&fields=size,killcode,serverid,md5hex&order=fileid") || "";

  if (not $result or $result =~ /^ERROR: /) { die "API Error occured: $result\n" }
  if ($result eq "NONE") { print "FINDDUPES: No dupe detected.\n"; return (0,0,0,0,0) }

  foreach (split(/\n/, $result)) {
    unless ($_ =~ /^(\d+),(\d+),(\d+),(\d+),(\w+)/) { die "FINDDUPES: Unexpected result: $result\n" }
    unless ($fileid) { $fileid = $1; $size = $2; $killcode = $3; $serverid = $4; $md5hex = lc($5); next }
    $dupefileids .= "$fileid,";
  }

  if ($dupefileids) {
    chop($dupefileids);

    if ($TRASHMODE == 1) {
      print "Moving duplicates to trash: $dupefileids\n";
      $result = get("http://api.rapidshare.com/cgi-bin/rsapi.cgi?login=$htmllogin&password=$htmlpassword&sub=movefilestorealfolder_v1&files=$dupefileids") || "";
      if ($result ne "OK") { die "FINDDUPES: Unexpected server reply: $result\n" }
    }

    elsif ($TRASHMODE == 2) {
      print "Deleting duplicates: $dupefileids\n";
      $result = get("http://api.rapidshare.com/cgi-bin/rsapi.cgi?login=$htmllogin&password=$htmlpassword&sub=deletefiles_v1&files=$dupefileids") || "";
      if ($result ne "OK") { die "DELETEFILE: Unexpected server reply: $result\n" }
    }
  }

  return ($fileid, $size, $killcode, $serverid, $md5hex);
}








sub uploadfile {
  my $file = shift || die;
  my $login = shift || "";
  my $password = shift || "";
  my $realfolder = shift || 0;

  my ($size, $md5obj, $size2, $readbytes, $data, $md5hex, $uploadserver, $cursize, $dupefileid, $dupesize, $dupekillcode, $dupemd5hex);

# This chapter checks the file and calculates the MD5HEX of the existing local file.
  $size = -s $file || die "File '$file' is empty or does not exist!\n";
  print "File $file has $size bytes. MD5=";

  if ($size > $CHUNKSIZE) {
    $md5hex = "SKIPPED";
  } else {
    open(FH, $file) || die "Unable to open file: $!\n";
    binmode(FH);
    $md5obj = Digest::MD5->new;
    $size2 = 0;
    while (($readbytes = read(FH, $data, 65536)) != 0) { $size2 += $readbytes; $md5obj->add($data) }
    close(FH);
    $md5hex = $md5obj->hexdigest; 
    unless ($size == $size2) { die "Strange error: $size byte found, but only $size2 byte analyzed?\n" }
  }

  print "$md5hex\n";

  if ($UPDATEMODE) {
    ($dupefileid, $dupesize, $dupekillcode, $uploadserver, $dupemd5hex) = &finddupes($login, $password, $realfolder, $file);
    if ($md5hex eq $dupemd5hex) { print "FILE ALREADY UP TO DATE! Server rs$uploadserver.rapidshare.com in file ID $dupefileid.\n\n"; return "" }
    if ($dupefileid) { print "UPDATING FILE $dupefileid on server rs$uploadserver.rapidshare.com\n" }
  }

  unless ($uploadserver) {
    $uploadserver = get("http://api.rapidshare.com/cgi-bin/rsapi.cgi?sub=nextuploadserver_v1") || "";
    if (not $uploadserver or $uploadserver =~ /^ERROR: /) { die "API Error occured: $uploadserver\n" }
    print "Uploading to rs$uploadserver.rapidshare.com\n";
  }

  $cursize = 0;

  while ($cursize < $size) { $cursize = &uploadchunk($file, $login, $password, $realfolder, $md5hex, $size, $cursize, "rs$uploadserver.rapidshare.com", $dupefileid, $dupekillcode) }

  return "";
}





sub uploadchunk {
  my $file = shift || die;
  my $login = shift || "";
  my $password = shift || "";
  my $realfolder = shift || 0;
  my $md5hex = shift || die;
  my $size = shift || die;
  my $cursize = shift || 0;
  my $fulluploadserver = shift || die;
  my $replacefileid = shift || 0;
  my $replacekillcode = shift || 0;
  my $bodtype = shift || 0;

  my ($uploaddata, $fh, $socket, $boundary, $contentheader, $contenttail, $contentlength, $header, $chunks, $chunksize,
$bufferlen, $buffer, $result, $fileid, $complete, $resumed, $filename, $killcode, $remotemd5hex, $chunkmd5hex);

  if (-e "$file.uploaddata") {
    open(I, "$file.uploaddata") or die "Unable to open file: $!\n";
    ($fulluploadserver, $fileid, $killcode) = split(/\n/, <I>);
    close(I);
    print "RESUMING UPLOAD! Server=$fulluploadserver File-ID=$fileid Start=$cursize\n";
    $cursize = get("http://api.rapidshare.com/cgi-bin/rsapi.cgi?sub=checkincomplete_v1&fileid=$fileid&killcode=$killcode") || "";
    unless ($cursize =~ /^\d+$/) { die "Unable to resume! Please delete $file.uploaddata or try again.\n" }
    $resumed = 1;
  }

  if ($size > $CHUNKSIZE) {
    $chunks = 1;
    $chunksize = $size - $cursize;
    if ($chunksize > $CHUNKSIZE) { $chunksize = $CHUNKSIZE } else { $complete = 1 }
  } else {
    $chunks = 0;
    $chunksize = $size;
  }

  sysopen($fh, $file, O_RDONLY) || die "Unable to open file: $!\n";
  $filename = $file =~ /[\/\\]([^\/\\]+)$/ ? $1 : $file;
  $socket = IO::Socket::INET->new(PeerAddr => "$fulluploadserver:80") || die "Unable to open socket: $!\n";
  $boundary = "---------------------632865735RS4EVER5675865";
  $contentheader .= qq|$boundary\r\nContent-Disposition: form-data; name="rsapi_v1"\r\n\r\n1\r\n|;

  if ($resumed) {
    $contentheader .= qq|$boundary\r\nContent-Disposition: form-data; name="fileid"\r\n\r\n$fileid\r\n|;
    $contentheader .= qq|$boundary\r\nContent-Disposition: form-data; name="killcode"\r\n\r\n$killcode\r\n|;
    if ($complete) { $contentheader .= qq|$boundary\r\nContent-Disposition: form-data; name="complete"\r\n\r\n1\r\n| }
  } else {
    $contentheader .= qq|$boundary\r\nContent-Disposition: form-data; name="login"\r\n\r\n$login\r\n|;
    $contentheader .= qq|$boundary\r\nContent-Disposition: form-data; name="password"\r\n\r\n$password\r\n|;
    $contentheader .= qq|$boundary\r\nContent-Disposition: form-data; name="realfolder"\r\n\r\n$realfolder\r\n|;
    $contentheader .= qq|$boundary\r\nContent-Disposition: form-data; name="replacefileid"\r\n\r\n$replacefileid\r\n|;
    $contentheader .= qq|$boundary\r\nContent-Disposition: form-data; name="replacekillcode"\r\n\r\n$replacekillcode\r\n|;
    $contentheader .= qq|$boundary\r\nContent-Disposition: form-data; name="bodtype"\r\n\r\n$bodtype\r\n|;

    if ($chunks) { $contentheader .= qq|$boundary\r\nContent-Disposition: form-data; name="incomplete"\r\n\r\n1\r\n| }
  }

  $contentheader .= qq|$boundary\r\nContent-Disposition: form-data; name="filecontent"; filename="$filename"\r\n\r\n|;
  $contenttail = "\r\n$boundary--\r\n";
  $contentlength = length($contentheader) + $chunksize + length($contenttail);

  if ($resumed) {
    $header = qq|POST /cgi-bin/uploadresume.cgi HTTP/1.1\r\nHost: $fulluploadserver\r\nContent-Type: multipart/form-data; boundary=$boundary\r\nContent-Length: $contentlength\r\n\r\n|;
  } else {
    $header = qq|POST /cgi-bin/upload.cgi HTTP/1.1\r\nHost: $fulluploadserver\r\nContent-Type: multipart/form-data; boundary=$boundary\r\nContent-Length: $contentlength\r\n\r\n|;
  }

  print $socket "$header$contentheader";

  sysseek($fh, $cursize, 0);
  $bufferlen = sysread($fh, $buffer, $CHUNKSIZE) || 0;
  unless ($bufferlen) { die "Error while reading file: $!\n" }
  $chunkmd5hex = md5_hex($buffer);
  print "Sending $bufferlen byte... ";
  $cursize += $bufferlen;
  print $socket $buffer;
  print $socket $contenttail;

  ($result) = <$socket> =~ /\r\n\r\n(.+)/s;
  unless ($result) { die "Ooops! Did not receive any valid server results?\n" }

  if ($resumed) {
    if ($complete) {
      if ($result =~ /^COMPLETE,(\w+)/) {
        print "Upload completed! Checking MD5...\nRemote MD5=$1 Local MD5=$md5hex\n";
        if ($chunkmd5hex ne $1 and $md5hex ne $1) { die "MD5 CHECK NOT PASSED!\n" }
        print "MD5 check passed. Upload OK! Saving status to rsapiuploads.txt\n\n";
        unlink("$file.uploaddata");
      } else {
        die "Unexpected server response!\n";
      }
    } else {
      if ($result =~ /^CHUNK,(\d+),(\w+)/) {
        print "Chunk upload completed! $1 byte uploaded.\nRemote MD5=$2 Local MD5=$chunkmd5hex\n\n";
        if ($chunkmd5hex ne $2) { die "CHUNK MD5 CHECK NOT PASSED!\n" }
      } else {
        die "Unexpected server response!\n\n$result\n";
      }
    }
  } else {
    if ($result =~ /files\/(\d+)/) { $fileid = $1 } else { die "Server result did not contain a file ID.\n$result" }
    unless ($result =~ /File1\.3=(\d+)/ and $1 == $cursize) { die "Server did not save all data we sent.\n$result" }
    unless ($result =~ /File1\.2=.+?killcode=(\d+)/) { die "Server did not send our killcode.\n$result" }
    $killcode = $1;
    unless ($result =~ /File1\.4=(\w+)/) { die "Server did not send the remote MD5 sum.\n" }
    $remotemd5hex = lc($1);

    if ($chunks) {
      if ($result !~ /File1\.5=Incomplete/) { die "Server did not acknowledge the incomplete upload request.\n" }
      print "Chunk upload completed! $cursize byte uploaded.\nRemote MD5=$remotemd5hex Local MD5=$chunkmd5hex\n";
      if ($remotemd5hex ne $chunkmd5hex) { die "CHUNK MD5 CHECK NOT PASSED!\n" }
      print "Upload OK! Saving to rsapiuploads.txt and resuming upload...\n\n";
      open(O, ">$file.uploaddata") or die "Unable to save upload server: $!\n";
      print O "$fulluploadserver\n$fileid\n$killcode\n";
      close(O);
    } else {
      if ($result !~ /File1\.5=Completed/) { die "Server did not acknowledge the completed upload request.\n" }
      if ($md5hex ne $remotemd5hex) { die "FINAL MD5 CHECK NOT PASSED! LOCAL=$md5hex REMOTE=$remotemd5hex\n" }
      print "FINAL MD5 check passed. Upload OK! Saving status to rsapiuploads.txt\n$result";
    }

    open(O,">>rsapiuploads.txt") or die "Unable to save to rsapiuploads.txt: $!\n";
    print O $chunks ? "Initialized chunk upload for file $file.\n$result" : "Uploaded file $file.\n$result";
    close(O);
  }

  return $cursize;
}





sub htmlencode {
  my $text = shift || "";

  unless (%ESCAPES) {
    for (0 .. 255) { $ESCAPES{chr($_)} = sprintf("%%%02X", $_) }
  }

  $text =~ s/(.)/$ESCAPES{$1}/g;

  return $text;
}