 #!/usr/bin/env python3

"""
This module provides functions to interact with the FAA NASR Subscription page.
It includes functions to extract archive links, current or preview NASR zip links,
and download files from given URLs.

Functions:
    article() -> bs4.element.Tag:
        Retrieves the main NASR page and finds the article element.

    list_archives() -> dict:
        Extracts and returns a dictionary of archive links from the NASR page.

    current_or_preview(which: str) -> dict:
        Extracts the NASR zip link from the specified section ('Preview' or 'Current').

    download(url: str, filename: str = None) -> str:
"""

import os
import re
import time
import urllib.request
import urllib.parse
import zipfile
import bs4
import platformdirs

_NASR_URL = 'https://www.faa.gov/air_traffic/flight_info/aeronav/aero_data/NASR_Subscription/'
_DEFAULT_FILENAME = 'downloaded_file'
_CACHE_PATH = platformdirs.user_cache_path("g3xfplan", "g3xfplan", ensure_exists=True)

def sanitize_filename(filename, max_length=255):
    """Sanitize a filename to prevent path traversal and other security issues."""
    if not filename:
        raise ValueError("Filename cannot be empty")

    # Extract just the filename part, handling URLs properly
    if '/' in filename:
        filename = filename.split('/')[-1]
    if '\\' in filename:
        filename = filename.split('\\')[-1]

    # Remove or replace dangerous characters
    # Keep only alphanumeric, dots, dashes, underscores
    filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)

    # Remove leading/trailing dots and spaces
    filename = filename.strip('. ')

    # Prevent empty filename
    if not filename or filename in ('.', '..'):
        filename = _DEFAULT_FILENAME

    # Ensure filename has reasonable length
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        if ext:
            filename = name[:max_length-len(ext)] + ext
        else:
            filename = filename[:max_length]

    return filename

def _article():
    # Get the main NASR page and find the article element
    url = _NASR_URL
    with urllib.request.urlopen(url) as response:
        html = response.read().decode('utf-8')
    soup = bs4.BeautifulSoup(html, 'html.parser')
    return soup.find('article', id='content')

def list_archives():
    """
    Extracts and returns a dictionary of archive links from a web page.
    The function searches for an 'Archives' section in the HTML content of an article,
    extracts the subscription effective date and corresponding link, and stores them
    in a dictionary.

    Returns:
        dict: A dictionary where the keys are subscription effective dates (as strings)
              and the values are the corresponding URLs (as strings).
    """

    # Initialize a dictionary to store the structured data
    dataurl = {}

    # Extract the fullzip link from the Archives section
    archives_section = _article().find('h2', string='Archives').find_next('ul')
    for li in archives_section.find_all('li'):
        text = li.contents[0].strip().lstrip('Subscription effective ').rstrip(' -')
        link = li.find('a')
        dataurl[text] = link['href']

    return dataurl

def current_or_preview(which):
    """
    Extracts the nasr zip link from the selected section.

    Args:
        which (str): The section to extract the link from. Can be 'Preview' or 'Current'.

    Returns:
        dict: A dictionary where the key is the subscription effective date (string)
              and the value is the corresponding URLs (string).
    """

    # Extract the fullzip link from the selected section
    for li in _article().find('h2', string=which).find_next('ul').find_all('li'):
        link = li.find('a')
        effective_date = link.text.lstrip('Subscription effective ')

        # Follow the link to get the fullzip and aptzip URLs
        subpage_url = urllib.parse.urljoin(_NASR_URL, link['href'])
        subpage_response = urllib.request.urlopen(subpage_url)
        subpage_html = subpage_response.read().decode('utf-8')
        subpage_soup = bs4.BeautifulSoup(subpage_html, 'html.parser')
        subpage_article = subpage_soup.find('article', id='content')
        fullzip_link = subpage_article.find('a', string='Download')['href']

    return {effective_date: fullzip_link}

def download(url, filename=None):
    """
    Downloads a file from the given URL and saves it to the specified filename.
    If the filename is not provided, the file will be saved with the basename of the URL.
    If the file already exists, the function will add an 'If-Modified-Since' header to the request
    to avoid downloading the file again if it has not been modified.

    Args:
        url (str): The URL of the file to download.
        filename (str, optional): The name of the file to save. Defaults to None.

    Returns:
        str: The filename of the downloaded file.

    Raises:
        urllib.error.HTTPError: If an HTTP error occurs other than a 304 Not Modified response.
    """

    # Create a request to retrieve the file
    request = urllib.request.Request(url)

    # Set filename with proper sanitization
    if filename:
        filename = sanitize_filename(filename)
    else:
        url_basename = os.path.basename(url)
        filename = sanitize_filename(url_basename) if url_basename else _DEFAULT_FILENAME

    # Ensure we're writing to cache directory
    filename = os.path.basename(filename)  # Extra safety measure
    filepath = _CACHE_PATH / filename

    # Check if the file already exists on the filesystem and add the If-Modified-Since header to the request
    if filepath.exists():
        last_modified_time = filepath.stat().st_mtime
        last_modified_time_str = time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(last_modified_time))
        request.add_header('If-Modified-Since', last_modified_time_str)

    # Download the file
    try:
        with urllib.request.urlopen(request) as response:
            if response.status == 200:
                with open(filepath, 'wb') as f:
                    f.write(response.read())

    except urllib.error.HTTPError as e:
        # Check if the server returned a 304 Not Modified response, if so, just skip the download
        if e.code != 304:
            raise

    return str(filepath)

class CsvZip():
    """
    A context manager class to handle the nested CSV ZIP file contained in the main ZIP archive.

    Attributes:
        filename (str): The path to the outer ZIP file.
        archive (zipfile.ZipFile): The outer ZIP file object.
        csv_archive (zipfile.ZipFile): The inner ZIP file object containing CSV data.

    Methods:
        __enter__(): Opens the outer ZIP file and the inner CSV ZIP file.
        __exit__(exc_type, exc_value, traceback): Closes the inner and outer ZIP files.
        namelist(): Returns a list of file names in the inner CSV ZIP file.
        open(name): Opens a file in the inner CSV ZIP file.
    """

    def __init__(self, filename):
        """
        Initializes the NASR object with the given filename.

        Args:
            filename (str): The name of the file to be processed.

        Attributes:
            filename (str): The name of the file to be processed.
            archive (None): Placeholder for the archive data.
            csv_archive (None): Placeholder for the CSV archive data.
        """
        self.filename = filename
        self.archive = None
        self.csv_archive = None

    def __enter__(self):
        """
        Enter the runtime context related to this object.
        This method is called when the execution flow enters the context of the
        `with` statement. It opens the main archive file specified by `self.filename`
        and then finds and opens the CSV data file within the archive.

        Returns:
            self: The instance of the class.
        """
        self.archive = zipfile.ZipFile(self.filename)

        # Find the CSV data file the archive
        csv_data_name = next(name for name in self.archive.namelist() if name.startswith('CSV_Data/') and name.endswith('.zip'))

        # Open the single file inside the CSV_Data folder as a new ZipFile
        self.csv_archive = zipfile.ZipFile(self.archive.open(csv_data_name))
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Exit the runtime context related to this object.
        This method is called when the 'with' statement is used. It closes the
        csv_archive and archive resources.
        """

        self.csv_archive.close()
        self.archive.close()

    def namelist(self):
        """
        Retrieve the list of filenames from the CSV archive.
        Returns:
            list: A list of names contained in the CSV archive.
        """
        return self.csv_archive.namelist()

    def open(self, name):
        """
        Open a file from the CSV archive.

        Parameters:
            name (str): The name of the file to open.

        Returns:
            file object: The opened file object from the CSV archive.
        """
        return self.csv_archive.open(name)
