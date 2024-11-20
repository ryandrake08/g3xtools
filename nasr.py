 #!/usr/bin/env python3

"""
This script downloads NASR (National Airspace System Resource) data from the FAA website.

Command Line Arguments:
    --list: Lists the available NASR data in the Archive section.
    --name: Downloads archived data by name.
    --preview: Downloads the Preview data.
    --current: Downloads the Current data.
    --filename: Specifies the NASR data filename. Uses basename of URL if not provided.

Usage:
    python nasr.py --list
    python nasr.py [ --name <name> | --preview | --current ]
    python nasr.py [ --name <name> | --preview | --current ] --filename <filename>

Raises:
    FileNotFoundError: If no data is found for the specified criteria.
    urllib.error.HTTPError: If there is an HTTP error during the download process.
"""

import argparse
import bs4
import os
import time
import urllib.request
import urllib.parse

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Download NASR data.')
    parser.add_argument('--list', action='store_true', help='List of NASR data in the Archive section.')
    parser.add_argument('--name', help='Download archived data by name.')
    parser.add_argument('--preview', action='store_true', help='Download the Preview data.')
    parser.add_argument('--current', action='store_true', help='Download the Current data.')
    parser.add_argument('--filename', help='Specify the NASR data filename. Uses basename of URL if not provided.')
    args = parser.parse_args()

    # Get the main NASR page and find the article element
    url = 'https://www.faa.gov/air_traffic/flight_info/aeronav/aero_data/NASR_Subscription/'
    response = urllib.request.urlopen(url)
    html = response.read().decode('utf-8')
    soup = bs4.BeautifulSoup(html, 'html.parser')
    article = soup.find('article', id='content')

    # Process the archive section
    if args.list or args.name:
        # Initialize a dictionary to store the structured data
        dataurl = {}

        # Extract the fullzip link from the Archives section
        archives_section = article.find('h2', string='Archives').find_next('ul')
        for li in archives_section.find_all('li'):
            text = li.contents[0].strip().lstrip('Subscription effective ').rstrip(' -')
            link = li.find('a')
            dataurl[text] = link['href']

        # List available NASR data if --list is passed, then exit
        if args.list:
            print('\n'.join(dataurl.keys()))
            return

        # Look up fullzip link by name
        if args.name:
            fullzip_link = dataurl.get(args.name)

    # Process the Preview or Current section
    if args.preview or args.current:

        # Decide which section to process
        selected_section = article.find('h2', string='Preview' if args.preview else 'Current').find_next('ul')

        # Extract the fullzip link from the selected section
        for li in selected_section.find_all('li'):
            link = li.find('a')
            args.name = link.text.lstrip('Subscription effective ')

            # Follow the link to get the fullzip and aptzip URLs
            subpage_url = urllib.parse.urljoin(url, link['href'])
            subpage_response = urllib.request.urlopen(subpage_url)
            subpage_html = subpage_response.read().decode('utf-8')
            subpage_soup = bs4.BeautifulSoup(subpage_html, 'html.parser')
            subpage_article = subpage_soup.find('article', id='content')
            fullzip_link = subpage_article.find('a', string='Download')['href']

    # Check if a fullzip link was found
    if not fullzip_link:
        raise FileNotFoundError('nasr: No data found.')

    # Create a request to retrieve the aptzip file
    request = urllib.request.Request(fullzip_link)

    # Set filename
    filename = args.filename or os.path.basename(fullzip_link)

    # Check if the file already exists on the filesystem
    if os.path.exists(filename):
        # Get the file's last modified timestamp
        last_modified_time = os.path.getmtime(filename)
        last_modified_time_str = time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(last_modified_time))

        # Add the If-Modified-Since header to the request
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

    print(filename)

if __name__ == '__main__':
    main()