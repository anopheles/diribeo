<h1>Downloads</h1>

%if downloads is not None and len(downloads) > 0:
    %if downloads.has_key("Rapidshare") and len(downloads["Rapidshare"]) >0:
        <h3>Rapidshare</h3>
        <table id="download" border="0">
        <th>Filename</th>
        <th>Date</th>
        <th>Download Size</th>
        <th>URL</th>
        %for properties in downloads["Rapidshare"]:
            <tr>
                 <td>Diribeo  {{properties["version_string"]}}</td>
                 <td>{{properties["date"]}}</td>
                 <td>{{"%0.5s" % (float(properties["size"])/1024**2)}} MB</td>
                 <td><a href="{{properties["url"]}}">{{properties["url"]}}</a></td>
            </tr>
        %end
        </table>
    <br>
    %end

    %if downloads.has_key("Hotfile") and len(downloads["Hotfile"]) >0:
        <h3>Hotfile (alternative mirror)</h3>
        <table id="download" border="0">
        <th>Filename</th>
        <th>URL</th>
        %for properties in downloads["Hotfile"]:
            <tr>
                 <td>Diribeo {{properties["version_string"]}}</td>
                 <td><a href="{{properties["url"]}}">{{properties["url"]}}</a></td>
            </tr>
        %end
        </table>
    %end
%else:
      Currently there are no downloads available
%end
%rebase main single_download=single_download

