#!/usr/bin/env python3

import requests
import json
import os
import sys
import argparse
import eyed3
import shutil
from datetime import datetime
from time import sleep

headers = {"User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:61.0) Gecko/20100101 Firefox/61.0"}


def detect_netease_music_name(song_id):
    # return song_id, None
    # url_base = "http://music.163.com/api/song/detail/?id={}&ids=[{}]"
    # url_target = url_base.format(song_id, song_id)
    url_base = 'http://music.163.com/api/v3/song/detail?id=%s&c=[{"id":"%s"}]'
    url_target = url_base % (song_id, song_id)

    resp = requests.get(url_target, headers=headers)
    retry_count = 10
    while resp.status_code != 200 and retry_count > 0:
        print(">>>> resp status_code is NOT 200, here song_id = %s, retry count = %d" % (song_id, retry_count))
        sleep(1)
        resp = requests.get(url_target, headers=headers)
        retry_count -= 1

    rr = resp.json()
    if rr["code"] == -460:
        print(">>>> Return with cheating in detect_netease_music_name, maybe it is expired time limit, try again later")
        exit(1)
    if len(rr.get("songs", "")) == 0:
        print(">>>> returned 200 OK, but song info is empty, remove it and try again, song_id = %s" % (song_id))
        exit(1)

    song_info = {}
    song_info["title"] = rr["songs"][0]["name"].replace("\xa0", " ")
    song_info["artist"] = rr["songs"][0]["ar"][0]["name"]
    song_info["album"] = rr["songs"][0]["al"]["name"]
    song_info["track_num"] = (int(rr["songs"][0]["no"]), int(rr["songs"][0]["cd"]))
    song_info["cover_image"] = rr["songs"][0]["al"]["picUrl"]
    song_info["id"] = song_id

    song_info["album_artist"] = rr["songs"][0]["ar"][0]["name"]
    publish_time = int(rr["songs"][0]["publishTime"])
    if publish_time == 0:
        url_album_base = "http://music.163.com/api/album/{}"
        url_album = url_album_base.format(rr["songs"][0]["al"]["id"])
        album_ret = requests.get(url_album, headers=headers).json()
        publish_time = int(album_ret["album"]["publishTime"])
    song_info["year"] = str(datetime.fromtimestamp(publish_time / 1000).year)

    return song_info, rr


def detect_netease_music_name_list(song_list):
    for song_id in song_list:
        ss, rr = detect_netease_music_name(song_id)
        ss.update({"song_id": song_id})
        yield ss


def netease_parse_playlist_2_list(playlist_id):
    # url_playlist_base = "http://music.163.com/api/playlist/detail?id={}"
    # url_playlist_base = "http://localhost:3000/playlist/detail?id={}"
    url_playlist_base = "https://music.163.com/api/v6/playlist/detail?id={}"
    url_playlist = url_playlist_base.format(playlist_id)

    resp = requests.get(url_playlist, headers=headers)
    rr = json.loads(resp.text)
    # play_list = rr["result"]["tracks"]
    # play_list = rr["playlist"]["tracks"]
    play_list = rr["playlist"]["trackIds"]

    for song_item in play_list:
        yield song_item["id"]


def netease_parse_album_2_list(album_id):
    url_album_base = "http://music.163.com/api/album/{}"
    # url_album_base = "https://music.163.com/weapi/vipmall/albumproduct/detail?id={}"
    url_album = url_album_base.format(album_id)

    resp = requests.get(url_album, headers=headers)
    for song_item in resp.json()["album"]["songs"]:
        yield song_item["id"]


def netease_cached_queue_2_list():
    cached_queue = os.path.expanduser("~/.cache/netease-cloud-music/StorageCache/webdata/file/queue")
    with open(cached_queue, "r") as ff:
        rr = json.load(ff)
    for song_item in rr:
        yield song_item["track"]["id"]


def netease_cached_queue_2_song_info():
    import json
    import requests
    from datetime import datetime

    cached_queue = os.path.expanduser("~/.cache/netease-cloud-music/StorageCache/webdata/file/queue")
    url_album_base = "http://music.163.com/api/album/{}"

    with open(cached_queue, "r") as ff:
        rr = json.load(ff)
    for song_item in rr:
        song_info = {}
        song_info["title"] = song_item["track"]["name"].replace("\xa0", " ")
        song_info["artist"] = song_item["track"]["artists"][0]["name"]
        song_info["album"] = song_item["track"]["album"]["name"]
        song_info["track_num"] = (int(song_item["track"]["position"]), int(song_item["track"]["cd"]))
        song_info["id"] = song_item["track"]["id"]
        song_info["cover_image"] = song_item["track"]["album"]["picUrl"]
        song_info["url"] = song_item.get("lastPlayInfo", {}).get("retJson", {}).get("url", None)

        url_album = url_album_base.format(song_item["track"]["album"]["id"])
        album_ret = requests.get(url_album, headers=headers).json()
        # print(url_album, album_ret["code"])
        song_info["year"] = str(datetime.fromtimestamp(int(album_ret["album"]["publishTime"]) / 1000).year)
        song_info["album_artist"] = album_ret["album"]["artist"]["name"]
        yield song_info


def generate_target_file_name(dist_path, title, artist, song_format="mp3"):
    aa = artist.replace("/", " ").replace(":", " ").replace("?", " ").strip()
    tt = title.replace("/", " ").replace(":", " ").replace("?", " ").strip()
    dist_name = os.path.join(dist_path, "%s - %s" % (aa, tt)) + "." + song_format

    return dist_name


def netease_cache_rename_single(song_id, file_path, dist_path, KEEP_SOURCE=True, song_format="mp3", SAVE_COVER_IAMGE=True):
    if not os.path.exists(dist_path):
        os.mkdir(dist_path)

    if not isinstance(song_id, dict):
        song_info, rr = detect_netease_music_name(song_id)
    else:
        song_info = song_id
        song_id = song_info["id"]
    try:
        tt = eyed3.load(file_path)
        tt.initTag()
        tt.tag.title = song_info["title"]
        tt.tag.artist = song_info["artist"]
        tt.tag.album = song_info["album"]
        tt.tag.album_artist = song_info["album_artist"]
        tt.tag.track_num = tuple(song_info["track_num"])
        tt.tag.recording_date = eyed3.core.Date.parse(song_info["year"])
        print(
            "song_id = %s, tt.tag {title = %s, artist = %s, album = %s, album_artist = %s, track_num = %s, year = %s}"
            % (song_id, tt.tag.title, tt.tag.artist, tt.tag.album, tt.tag.album_artist, tt.tag.track_num, song_info["year"])
        )

        if SAVE_COVER_IAMGE:
            pic_url = song_info["cover_image"]
            resp = requests.get(pic_url)
            tt.tag.images.set(3, resp.content, "image/jpeg", "album cover")
        tt.tag.save(encoding="utf8")
    except UnicodeDecodeError as err:
        print("EyeD3 decode error: %s" % err)

    dist_name = generate_target_file_name(dist_path, song_info["title"], song_info["artist"], song_format)

    if KEEP_SOURCE == True:
        shutil.copyfile(file_path, dist_name)
    else:
        os.rename(file_path, dist_name)

    return dist_name


def netease_cache_rename(source_path, dist_path, KEEP_SOURCE=True):
    for file_name in os.listdir(source_path):
        if not file_name.endswith(".mp3"):
            continue
        if not len(file_name.split("-")) == 3:
            print(">>>> File %s not in format <song id>-<bite rate>-<random number>.mp3" % (file_name))
            continue

        song_id = file_name.split("-")[0]
        netease_cache_rename_single(song_id, os.path.join(source_path, file_name), dist_path, KEEP_SOURCE)


def parse_arguments(argv):
    HOME_DIR = os.getenv("HOME")
    default_source_path = os.path.join(HOME_DIR, ".cache/netease-cloud-music/CachedSongs")
    default_dist_path = "./output_music"

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Rename netease-cloud-music Ubuntu client cached files\n"
            "From: source_path/<song id>-<bite rate>-<random number>.mp3\n"
            "To: dist_path/<artist name> - <song title>.mp3\n"
            "\n"
            "default source path: %s\n"
            "default dist path: %s" % (default_source_path, default_dist_path)
        ),
    )
    parser.add_argument("-d", "--dist_path", type=str, help="Music output path", default=default_dist_path)
    parser.add_argument("-s", "--source_path", type=str, help="Music source path", default=default_source_path)
    parser.add_argument(
        "-r", "--remove_source", action="store_true", help="Remove source files, default using cp instead of mv"
    )
    parser.add_argument(
        "--song_id_list", nargs="*", type=str, help="Specify song id list to detect song name. Format 1 2 3 or 1, 2, 3"
    )

    args = parser.parse_args(argv)
    args.keep_source = not args.remove_source
    return args


if __name__ == "__main__":
    args = parse_arguments(sys.argv[1:])
    if args.song_id_list == None or len(args.song_id_list) == 0:
        print("source = %s, dist = %s" % (args.source_path, args.dist_path))
        netease_cache_rename(args.source_path, args.dist_path, args.keep_source)
    else:
        song_id_list = [int(ss.replace(",", "")) for ss in args.song_id_list]
        for ss in detect_netease_music_name_list(song_id_list):
            print("    %s: %s - %s" % (ss["song_id"], ss["artist"], ss["title"]))
