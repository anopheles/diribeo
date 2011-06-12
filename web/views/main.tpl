<!doctype html>
<html>
<head>
  <title>Diribeo - Series Organizer</title>
  <link rel="stylesheet" type="text/css" href="/stylesheets/styles.css"/>
</head>
<body>
	
	<section id="logo">
		<header>
			<a href="/"><img width=300 src="/images/diribeo_logo.png" border="0"></a>
		</header>
	</section>
	
	<nav>
        <ul>
            <li><a href="overview">Overview</a></li>
            <li><a href="downloads">Downloads</a></li>
            <li><a href="tutorial">Tutorial</a></li>
            <li><a href="contribute">Contribute</a></li>
            <li><a href="faq">FAQ</a></li>
            <li><a href="contact">Contact</a></li>
        </ul>
	</nav>

    % if single_download is not None:
	<section id="intro"> 
		<header> 
			<h2>Diribeo</h2>
			<p>Diribeo is a simple but powerful utility for organizing your series collection.</p>
			<br>
		<a href={{single_download["url"]}} class="button green">Download Version {{single_download["version"]}} win32</a>
		</header> 
		<img src="/images/intro_flower.png" alt="intro" />
	</section>
    % end
	
	<section>
		<article class="blogPost">  
    		%include
   		 </article> 
		 <br><br>		 
	</section>
	<footer> 
		%include footer
	</footer> 

</body>
</html>
