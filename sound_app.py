from __future__ import unicode_literals

import os
import re
import requests
import soundcloud
import sys
import urllib
import json
import datetime, time

from clint.textui import colored, puts, progress, indent
from datetime import datetime
from mutagen.mp3 import MP3, EasyMP3
from mutagen.id3 import APIC, WXXX
from mutagen.id3 import ID3 as OldID3
from os.path import dirname, exists, join
from os import access, mkdir, W_OK

#configloader
def _load_file(fname):
    if os.path.isfile(fname):
        with open(fname, 'r') as f:
            return json.loads(f.read())

####################################################################
dir_path = os.path.dirname(os.path.realpath(__file__))
loader = _load_file('db/soundcloud_config.json')
CLIENT_ID = _load_file('db/soundcloud_config.json')['soundcloud']['CLIENT_ID']
AGGRESSIVE_CLIENT_ID = _load_file('db/soundcloud_config.json')['soundcloud']['AGGRESSIVE_CLIENT_ID']
APP_VERSION = _load_file('db/soundcloud_config.json')['soundcloud']['APP_VERSION']
vargs = _load_file('db/soundcloud_config.json')['vargs']
####################################################################

def console_msg():
    if sys.platform == "win32":
        os.system("chcp 65001")
        os.system("cls")
    
    files = os.listdir(path='%s\music' % dir_path)
    puts(colored.yellow('SOUNDCLOUD DOWNLOADER v 1.0'))
    lines = [
        ">" * 50,
        "> AUTHOR: %s" % loader['AUTHOR'],
        "> APP_VERSION: %s" % APP_VERSION,
        "> CLIENT_ID: %s" % CLIENT_ID,
        "> AGGRESSIVE_ID: %s" % AGGRESSIVE_CLIENT_ID,
        "> CLIENT_SECRET: %s" % loader['soundcloud']['CLIENT_SECRET'],
        "> PATH: %s\music" % dir_path,
        "> DATE: %s" % time.ctime(int(time.time())),
        ">" * 50,
        "\n"
        ]
        
    for x in lines:
            with indent(1):
                puts(x)
    print(' ==PLAYLIST(%s)==' % files.__len__())            
    for file in files:
            with indent(1):
                puts(file)

def main():
    # Hack related to #58
    console_msg()
    
    if vargs['debug'] == True:
            URL = input(colored.green('URL/Link: '))
            vargs['artist_url'] = [URL.split('?')[0]]
    else:
            vargs['artist_url'] = [sys.argv[1]]
            print(vargs['artist_url'])

    if not vargs['artist_url']:
        print('Please supply an artist\'s username or URL!')

    if sys.version_info < (3,0,0):
        vargs['artist_url'] = urllib.quote(vargs['artist_url'][0], safe=':/')
    else:
        vargs['artist_url'] = urllib.parse.quote(vargs['artist_url'][0], safe=':/')

    artist_url = vargs['artist_url']

    if not exists(vargs['path']):
        if not access(dirname(vargs['path']), W_OK):
            vargs['path'] = '%s/music' % dir_path
        else:
            mkdir(vargs['path'])

        os.system("CLS")
        process_soundcloud(vargs)
        

####################################################################
# SoundCloud
####################################################################


def process_soundcloud(vargs):
    """
    Main SoundCloud path.
    """

    artist_url = vargs['artist_url']
    track_permalink = vargs['track']
    keep_previews = vargs['keep']
    folders = vargs['folders']

    id3_extras = {}
    one_track = False
    likes = False
    client = get_client()
    if 'soundcloud' not in artist_url.lower():
        if vargs['group']:
            artist_url = 'https://soundcloud.com/groups/' + artist_url.lower()
        elif len(track_permalink) > 0:
            one_track = True
            track_url = 'https://soundcloud.com/' + artist_url.lower() + '/' + track_permalink.lower()
        else:
            artist_url = 'https://soundcloud.com/' + artist_url.lower()
            if vargs['likes'] or 'likes' in artist_url.lower():
                likes = True

    if 'likes' in artist_url.lower():
        artist_url = artist_url[0:artist_url.find('/likes')]
        likes = True

    if one_track:
        num_tracks = 1
    else:
        num_tracks = vargs['num_tracks']

    try:
        if one_track:
            resolved = client.get('/resolve', url=track_url, limit=200)

        elif likes:
            userId = str(client.get('/resolve', url=artist_url).id)

            resolved = client.get('/users/' + userId + '/favorites', limit=200, linked_partitioning=1)
            next_href = False
            if(hasattr(resolved, 'next_href')):
                next_href = resolved.next_href
            while (next_href):

                resolved2 = requests.get(next_href).json()
                if('next_href' in resolved2):
                    next_href = resolved2['next_href']
                else:
                    next_href = False
                resolved2 = soundcloud.resource.ResourceList(resolved2['collection'])
                resolved.collection.extend(resolved2)
            resolved = resolved.collection

        else:
            resolved = client.get('/resolve', url=artist_url, limit=200)

    except Exception as e:  # HTTPError?

        # SoundScrape is trying to prevent us from downloading this.
        # We're going to have to stop trusting the API/client and
        # do all our own scraping. Boo.

        if '404 Client Error' in str(e):
            puts(colored.red("Problem downloading [404]: ") + colored.white("Item Not Found"))
            return None

        message = str(e)
        item_id = message.rsplit('/', 1)[-1].split('.json')[0].split('?client_id')[0]
        hard_track_url = get_hard_track_url(item_id)

        track_data = get_soundcloud_data(artist_url)
        puts_safe(colored.green("Scraping") + colored.white(": " + track_data['title']))

        filenames = []
        filename = sanitize_filename(track_data['artist'] + ' - ' + track_data['title'] + '.mp3')

        if folders:
            name_path = join(vargs['path'], track_data['artist'])
            if not exists(name_path):
                mkdir(name_path)
            filename = join(name_path, filename)
        else:
            filename = join(vargs['path'], filename)

        if exists(filename):
            puts_safe(colored.yellow("Track already downloaded: ") + colored.white(track_data['title']))
            return None

        filename = download_file(hard_track_url, filename)
        tagged = tag_file(filename,
                 artist=track_data['artist'],
                 title=track_data['title'],
                 year='2018',
                 genre='',
                 album='',
                 artwork_url='')

        if not tagged:
            wav_filename = filename[:-3] + 'wav'
            os.rename(filename, wav_filename)
            filename = wav_filename

        filenames.append(filename)

    else:

        aggressive = False

        # This is is likely a 'likes' page.
        if not hasattr(resolved, 'kind'):
            tracks = resolved
        else:
            if resolved.kind == 'artist':
                artist = resolved
                artist_id = str(artist.id)
                tracks = client.get('/users/' + artist_id + '/tracks', limit=200)
            elif resolved.kind == 'playlist':
                id3_extras['album'] = resolved.title
                if resolved.tracks != []:
                    tracks = resolved.tracks
                else:
                    tracks = get_soundcloud_api_playlist_data(resolved.id)['tracks']
                    tracks = tracks[:num_tracks]
                    aggressive = True
                    for track in tracks:
                        download_track(track, resolved.title, keep_previews, folders, custom_path=vargs['path'])

            elif resolved.kind == 'track':
                tracks = [resolved]
            elif resolved.kind == 'group':
                group = resolved
                group_id = str(group.id)
                tracks = client.get('/groups/' + group_id + '/tracks', limit=200)
            else:
                artist = resolved
                artist_id = str(artist.id)
                tracks = client.get('/users/' + artist_id + '/tracks', limit=200)
                if tracks == [] and artist.track_count > 0:
                    aggressive = True
                    filenames = []

                    # this might be buggy
                    data = get_soundcloud_api2_data(artist_id)

                    for track in data['collection']:

                        if len(filenames) >= num_tracks:
                            break

                        if track['type'] == 'playlist':
                            track['playlist']['tracks'] = track['playlist']['tracks'][:num_tracks]
                            for playlist_track in track['playlist']['tracks']:
                                album_name = track['playlist']['title']
                                filename = download_track(playlist_track, album_name, keep_previews, folders, filenames, custom_path=vargs['path'])
                                if filename:
                                    filenames.append(filename)
                        else:
                            d_track = track['track']
                            filename = download_track(d_track, custom_path=vargs['path'])
                            if filename:
                                filenames.append(filename)

        if not aggressive:
            filenames = download_tracks(client, tracks, num_tracks, vargs['downloadable'], vargs['folders'], vargs['path'],
                                        id3_extras=id3_extras)

    if vargs['open']:
        open_files(filenames)


def get_client():
    """
    Return a new SoundCloud Client object.
    """
    client = soundcloud.Client(client_id=CLIENT_ID)
    return client

def download_track(track, album_name=u'', keep_previews=False, folders=False, filenames=[], custom_path=''):
    """
    Given a track, force scrape it.
    """

    hard_track_url = get_hard_track_url(track['id'])

    # We have no info on this track whatsoever.
    if not 'title' in track:
        return None

    if not keep_previews:
        if (track.get('duration', 0) < track.get('full_duration', 0)):
            puts_safe(colored.yellow("Skipping preview track") + colored.white(": " + track['title']))
            return None

    # May not have a "full name"
    name = track['user'].get('full_name', '')
    if name == '':
        name = track['user']['username']

    filename = sanitize_filename(name + ' - ' + track['title'] + '.mp3')

    if folders:
        name_path = join(custom_path, name)
        if not exists(name_path):
            mkdir(name_path)
        filename = join(name_path, filename)
    else:
        filename = join(custom_path, filename)

    if exists(filename):
        puts_safe(colored.yellow("Track already downloaded: ") + colored.white(track['title']))
        return None

    # Skip already downloaded track.
    if filename in filenames:
        return None

    if hard_track_url:
        puts_safe(colored.green("Scraping") + colored.white(": " + track['title']))
    else:
        # Region coded?
        puts_safe(colored.yellow("Unable to download") + colored.white(": " + track['title']))
        return None

    filename = download_file(hard_track_url, filename)
    tagged = tag_file(filename,
             artist=name,
             title=track['title'],
             year=track['created_at'][:4],
             genre=track['genre'],
             album=album_name,
             artwork_url=track['artwork_url'])
    if not tagged:
        wav_filename = filename[:-3] + 'wav'
        os.rename(filename, wav_filename)
        filename = wav_filename

    return filename

def download_tracks(client, tracks, num_tracks=sys.maxsize, downloadable=False, folders=False, custom_path='', id3_extras={}):
    """
    Given a list of tracks, iteratively download all of them.

    """

    filenames = []

    for i, track in enumerate(tracks):

        # "Track" and "Resource" objects are actually different,
        # even though they're the same.
        if isinstance(track, soundcloud.resource.Resource):

            try:

                t_track = {}
                t_track['downloadable'] = track.downloadable
                t_track['streamable'] = track.streamable
                t_track['title'] = track.title
                t_track['user'] = {'username': track.user['username']}
                t_track['release_year'] = track.release
                t_track['genre'] = track.genre
                t_track['artwork_url'] = track.artwork_url
                if track.downloadable:
                    t_track['stream_url'] = track.download_url
                else:
                    if downloadable:
                        puts_safe(colored.red("Skipping") + colored.white(": " + track.title))
                        continue
                    if hasattr(track, 'stream_url'):
                        t_track['stream_url'] = track.stream_url
                    else:
                        t_track['direct'] = True
                        streams_url = "https://api.soundcloud.com/i1/tracks/%s/streams?client_id=%s&app_version=%s" % (
                        str(track.id), AGGRESSIVE_CLIENT_ID, APP_VERSION)
                        response = requests.get(streams_url).json()
                        t_track['stream_url'] = response['http_mp3_128_url']

                track = t_track
            except Exception as e:
                puts_safe(colored.white(track.title) + colored.red(' is not downloadable.'))
                continue

        if i > num_tracks - 1:
            continue
        try:
            if not track.get('stream_url', False):
                puts_safe(colored.white(track['title']) + colored.red(' is not downloadable.'))
                continue
            else:
                track_artist = sanitize_filename(track['user']['username'])
                track_title = sanitize_filename(track['title'])
                track_filename = track_artist + ' - ' + track_title + '.mp3'

                if folders:
                    track_artist_path = join(custom_path, track_artist)
                    if not exists(track_artist_path):
                        mkdir(track_artist_path)
                    track_filename = join(track_artist_path, track_filename)
                else:
                    track_filename = join(custom_path, track_filename)

                if exists(track_filename):
                    puts_safe(colored.yellow("Track already downloaded: ") + colored.white(track_title))
                    continue

                puts_safe(colored.green("Downloading") + colored.white(": " + track['title']))


                if track.get('direct', False):
                    location = track['stream_url']
                else:
                    stream = client.get(track['stream_url'], allow_redirects=False, limit=200)
                    if hasattr(stream, 'location'):
                        location = stream.location
                    else:
                        location = stream.url

                filename = download_file(location, track_filename)
                tagged = tag_file(filename,
                         artist=track['user']['username'],
                         title=track['title'],
                         year=track['release_year'],
                         genre=track['genre'],
                         album=id3_extras.get('album', None),
                         artwork_url=track['artwork_url'])

                if not tagged:
                    wav_filename = filename[:-3] + 'wav'
                    os.rename(filename, wav_filename)
                    filename = wav_filename

                filenames.append(filename)
        except Exception as e:
            puts_safe(colored.red("Problem downloading ") + colored.white(track['title']))
            puts_safe(str(e))

    return filenames



def get_soundcloud_data(url):
    """
    Scrapes a SoundCloud page for a track's important information.

    Returns:
        dict: of audio data

    """

    data = {}

    request = requests.get(url)

    title_tag = request.text.split('<title>')[1].split('</title')[0]
    data['title'] = title_tag.split(' by ')[0].strip()
    data['artist'] = title_tag.split(' by ')[1].split('|')[0].strip()
    # XXX Do more..

    return data


def get_soundcloud_api2_data(artist_id):
    """
    Scrape the new API. Returns the parsed JSON response.
    """

    v2_url = "https://api-v2.soundcloud.com/stream/users/%s?limit=500&client_id=%s&app_version=%s" % (
    artist_id, AGGRESSIVE_CLIENT_ID, APP_VERSION)
    response = requests.get(v2_url)
    parsed = response.json()

    return parsed

def get_soundcloud_api_playlist_data(playlist_id):
    """
    Scrape the new API. Returns the parsed JSON response.
    """

    url = "https://api.soundcloud.com/playlists/%s?representation=full&client_id=02gUJC0hH2ct1EGOcYXQIzRFU91c72Ea&app_version=1467724310" % (
        playlist_id)
    response = requests.get(url)
    parsed = response.json()

    return parsed

def get_hard_track_url(item_id):
    """
    Hard-scrapes a track.
    """

    streams_url = "https://api.soundcloud.com/i1/tracks/%s/streams/?client_id=%s&app_version=%s" % (
    item_id, AGGRESSIVE_CLIENT_ID, APP_VERSION)
    response = requests.get(streams_url)
    json_response = response.json()

    if response.status_code == 200:
        hard_track_url = json_response['http_mp3_128_url']
        return hard_track_url
    else:
        return None


####################################################################
# File Utility
####################################################################


def download_file(url, path, session=None, params=None):
    """
    Download an individual file.
    """

    if url[0:2] == '//':
        url = 'https://' + url[2:]

    # Use a temporary file so that we don't import incomplete files.
    tmp_path = path + '.tmp'

    if session and params:
        r = session.get( url, params=params, stream=True )
    elif session and not params:
        r = session.get( url, stream=True )
    else:
        r = requests.get(url, stream=True)
    with open(tmp_path, 'wb') as f:
        total_length = int(r.headers.get('content-length', 0))
        for chunk in progress.bar(r.iter_content(chunk_size=1024), expected_size=(total_length / 1024) + 1):
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)
                f.flush()

    os.rename(tmp_path, path)

    return path


def tag_file(filename, artist, title, year=None, genre=None, artwork_url=None, album=None, track_number=None, url=None):
    """
    Attempt to put ID3 tags on a file.

    Args:
        artist (str):
        title (str):
        year (int):
        genre (str):
        artwork_url (str):
        album (str):
        track_number (str):
        filename (str):
        url (str):
    """

    try:
        audio = EasyMP3(filename)
        audio.tags = None
        audio["artist"] = artist
        audio["title"] = title
        if year:
            audio["date"] = str(year)
        if album:
            audio["album"] = album
        if track_number:
            audio["tracknumber"] = track_number
        if genre:
            audio["genre"] = genre
        if url: # saves the tag as WOAR
            audio["website"] = url
        audio.save()

        if artwork_url:

            artwork_url = artwork_url.replace('https', 'http')

            mime = 'image/jpeg'
            if '.jpg' in artwork_url:
                mime = 'image/jpeg'
            if '.png' in artwork_url:
                mime = 'image/png'

            if '-large' in artwork_url:
                new_artwork_url = artwork_url.replace('-large', '-t500x500')
                try:
                    image_data = requests.get(new_artwork_url).content
                except Exception as e:
                    # No very large image available.
                    image_data = requests.get(artwork_url).content
            else:
                image_data = requests.get(artwork_url).content

            audio = MP3(filename, ID3=OldID3)
            audio.tags.add(
                APIC(
                    encoding=3,  # 3 is for utf-8
                    mime=mime,
                    type=3,  # 3 is for the cover image
                    desc='Cover',
                    data=image_data
                )
            )
            audio.save()

        # because there is software that doesn't seem to use WOAR we save url tag again as WXXX
        if url:
            audio = MP3(filename, ID3=OldID3)
            audio.tags.add( WXXX( encoding=3, url=url ) )
            audio.save()

        return True

    except Exception as e:
        puts(colored.red("Problem tagging file: ") + colored.white("Is this file a WAV?"))
        return False

def open_files(filenames):
    """
    Call the system 'open' command on a file.
    """
    command = ['open'] + filenames
    process = Popen(command, stdout=PIPE, stderr=PIPE)
    stdout, stderr = process.communicate()


def sanitize_filename(filename):
    """
    Make sure filenames are valid paths.

    Returns:
        str:
    """
    sanitized_filename = re.sub(r'[/\\:*?"<>|]', '-', filename)
    sanitized_filename = sanitized_filename.replace('&', 'and')
    sanitized_filename = sanitized_filename.replace('"', '')
    sanitized_filename = sanitized_filename.replace("'", '')
    sanitized_filename = sanitized_filename.replace("/", '')
    sanitized_filename = sanitized_filename.replace("\\", '')

    # Annoying.
    if sanitized_filename[0] == '.':
        sanitized_filename = u'dot' + sanitized_filename[1:]

    return sanitized_filename

def puts_safe(text):
    if sys.platform == "win32":
        if sys.version_info < (3,0,0):
            puts(text)
        else:
            puts(text.encode(sys.stdout.encoding, errors='replace').decode())
    else:
        puts(text)


####################################################################
# Main
####################################################################

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print(e)