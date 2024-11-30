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
import time
import urllib.request
import urllib.parse
import bs4

_NASR_URL = 'https://www.faa.gov/air_traffic/flight_info/aeronav/aero_data/NASR_Subscription/'

def _article():
    # Get the main NASR page and find the article element
    url = _NASR_URL
    response = urllib.request.urlopen(url)
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

    # Set filename
    filename = filename or os.path.basename(url)

    # Check if the file already exists on the filesystem and add the If-Modified-Since header to the request
    if os.path.exists(filename):
        last_modified_time = os.path.getmtime(filename)
        last_modified_time_str = time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(last_modified_time))
        request.add_header('If-Modified-Since', last_modified_time_str)

    # Download the file
    try:
        with urllib.request.urlopen(request) as response:
            if response.status == 200:
                with open(filename, 'wb') as f:
                    f.write(response.read())

    except urllib.error.HTTPError as e:
        # Check if the server returned a 304 Not Modified response, if so, just skip the download
        if e.code != 304:
            raise

    return filename
