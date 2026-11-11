#!/usr/bin/env python3
"""
Music Metadata Tagger
=====================
Automatically scans music files, fetches accurate metadata (Title, Artist, Album,
Year, Genre, and Cover Art) from online music databases (iTunes API & Shazam
Fingerprinting fallback), and updates audio tags seamlessly.

Supported Formats:
- MP3 (.mp3) - via ID3v2.3/v2.4
- AAC / M4A (.m4a, .mp4) - via MP4 atoms
- FLAC (.flac) - via Vorbis comments & FLAC pictures
"""

import os
import re
import sys
import time
import argparse
from typing import Optional, Dict, Any, List
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Audio tagging libraries
from mutagen import File
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC, PictureType, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover
from mutagen.flac import FLAC, Picture
from mutagen.mp3 import MP3

# Ensure UTF-8 output on Windows consoles
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


# Configure requests session with resilient retries
session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))


def clean_search_string(text: str) -> str:
    """Clean filenames and track titles from extra video/release baggage."""
    if not text:
        return ""
    patterns = [
        r'\(feat\.[^\)]+\)',
        r'\[feat\.[^\]]+\]',
        r'\(ft\.[^\)]+\)',
        r'\(from the motion picture[^\)]+\)',
        r'\[from the motion picture[^\]]+\]',
        r'\(official[^\)]+\)',
        r'\[official[^\)]+\]',
        r'\(audio[^\)]+\)',
        r'\[audio[^\]]+\]',
        r'\(lyrics[^\)]+\)',
        r'\[lyrics[^\]]+\]',
        r'\(music video[^\)]+\)',
        r'\(made popular by[^\)]+\)',
        r'\[vocal version\]',
        r'\(In the Style of[^\)]+\)',
        r'\[Karaoke Version\]',
    ]
    for p in patterns:
        text = re.sub(p, '', text, flags=re.IGNORECASE)
    
    text = text.replace('_', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def parse_filename(filepath: str) -> tuple[Optional[str], Optional[str]]:
    """Attempt to parse Artist and Title from filename pattern 'Artist - Title'."""
    base = os.path.splitext(os.path.basename(filepath))[0]
    if ' - ' in base:
        parts = base.split(' - ', 1)
        return clean_search_string(parts[0]), clean_search_string(parts[1])
    return None, clean_search_string(base)


def is_hashed_filename(name: str) -> bool:
    """Detect if filename is random hash, uuid, or default download name."""
    base = os.path.splitext(os.path.basename(name))[0].lower()
    if re.match(r'^(dlls_|uuid_|track|audio|sound|song|download|[0-9a-f]{16,})', base):
        return True
    if len(base) > 20 and not ' ' in base and '-' not in base:
        return True
    return False


def search_itunes(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Query the iTunes Search API for song metadata."""
    url = 'https://itunes.apple.com/search'
    params = {'term': query, 'entity': 'song', 'limit': limit}
    try:
        resp = session.get(url, params=params, timeout=12)
        if resp.status_code == 200:
            return resp.json().get('results', [])
    except Exception as e:
        print(f"  [!] Search error for '{query}': {e}", file=sys.stderr)
    return []


def recognize_audio_shazam(filepath: str) -> Optional[Dict[str, Any]]:
    """Use Shazam acoustic fingerprinting to identify unknown or hash-named songs."""
    try:
        import warnings
        warnings.filterwarnings('ignore')
        from shazamio import Shazam
        import asyncio
        import io
        
        async def _run():
            shazam = Shazam()
            return await shazam.recognize(filepath)
            
        # Suppress noisy unclosed aiohttp session warnings on Windows
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            out = asyncio.run(_run())
        finally:
            sys.stderr = old_stderr
        track = out.get('track', {})
        if track and track.get('title'):
            title = track.get('title')
            artist = track.get('subtitle')
            genre = track.get('genres', {}).get('primary')
            album = None
            year = None
            for sec in track.get('sections', []):
                if sec.get('type') == 'SONG':
                    for meta in sec.get('metadata', []):
                        if meta.get('title') == 'Album':
                            album = meta.get('text')
                        elif meta.get('title') == 'Released':
                            year = meta.get('text')[:4]
            art_url = track.get('images', {}).get('coverart')
            if art_url:
                art_url = art_url.replace('400x400cc.jpg', '600x600bb.jpg')
            return {
                'title': title,
                'artist': artist,
                'album': album or f"{title} - Single",
                'date': year,
                'genre': genre,
                'art_url': art_url,
                'matched_query': 'Shazam Audio Fingerprint'
            }
    except Exception:
        pass
    return None


def check_has_artwork(filepath: str) -> bool:
    """Check if the audio file already contains embedded cover art."""
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == '.mp3':
            id3 = ID3(filepath)
            return any(k.startswith('APIC') for k in id3.keys())
        elif ext in ('.m4a', '.mp4'):
            mp4 = MP4(filepath)
            return bool(mp4.get('covr'))
        elif ext == '.flac':
            flac = FLAC(filepath)
            return len(flac.pictures) > 0
    except Exception:
        pass
    return False


def get_current_metadata(filepath: str) -> Dict[str, Any]:
    """Retrieve existing metadata tags from the audio file."""
    info = {'title': None, 'artist': None, 'album': None, 'date': None, 'genre': None}
    try:
        audio = File(filepath, easy=True)
        if audio:
            for k in info.keys():
                val = audio.get(k)
                if val:
                    info[k] = val[0] if isinstance(val, (list, tuple)) else str(val)
    except Exception:
        pass
    return info


def find_best_metadata(filepath: str, curr_meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Search online databases using multiple fallback strategies to find accurate metadata.
    """
    fn_artist, fn_title = parse_filename(filepath)
    artist = curr_meta.get('artist') or fn_artist
    title = curr_meta.get('title') or fn_title

    queries = []
    # If the filename or tags are not hashed
    if not is_hashed_filename(filepath):
        if artist and title:
            queries.append(f"{artist} {clean_search_string(title)}")
            queries.append(f"{clean_search_string(artist)} {clean_search_string(title)}")
        if fn_title:
            queries.append(fn_title)
        
        for q in queries:
            results = search_itunes(q)
            if results:
                best = results[0]
                track_name = best.get('trackName')
                artist_name = best.get('artistName')
                album_name = best.get('collectionName')
                raw_date = best.get('releaseDate')
                genre = best.get('primaryGenreName')
                art_url = best.get('artworkUrl100')
                
                if art_url:
                    art_url = art_url.replace('100x100bb.jpg', '600x600bb.jpg')

                year = raw_date[:4] if raw_date else None

                return {
                    'title': track_name,
                    'artist': artist_name,
                    'album': album_name,
                    'date': year,
                    'genre': genre,
                    'art_url': art_url,
                    'matched_query': q
                }
            time.sleep(0.2)

    # Fallback to Shazam Audio Fingerprinting if text queries fail or file is a hash
    print(f"  -> Identifying audio via acoustic fingerprint...")
    shazam_match = recognize_audio_shazam(filepath)
    if shazam_match:
        # Also double check iTunes for high-res metadata using the Shazam title & artist
        itunes_refine = search_itunes(f"{shazam_match['artist']} {shazam_match['title']}", limit=1)
        if itunes_refine:
            best = itunes_refine[0]
            shazam_match['album'] = best.get('collectionName') or shazam_match['album']
            raw_date = best.get('releaseDate')
            if raw_date:
                shazam_match['date'] = raw_date[:4]
            shazam_match['genre'] = best.get('primaryGenreName') or shazam_match['genre']
            art_url = best.get('artworkUrl100')
            if art_url:
                shazam_match['art_url'] = art_url.replace('100x100bb.jpg', '600x600bb.jpg')
        return shazam_match

    return None


def apply_tags(filepath: str, metadata: Dict[str, Any], overwrite_existing: bool = False, embed_art: bool = True) -> bool:
    """Write metadata tags and optional artwork to the audio file."""
    ext = os.path.splitext(filepath)[1].lower()
    curr = get_current_metadata(filepath)
    has_art = check_has_artwork(filepath)

    title = metadata.get('title') if (overwrite_existing or not curr.get('title')) else curr.get('title')
    artist = metadata.get('artist') if (overwrite_existing or not curr.get('artist')) else curr.get('artist')
    album = metadata.get('album') if (overwrite_existing or not curr.get('album')) else curr.get('album')
    date = metadata.get('date') if (overwrite_existing or not curr.get('date')) else curr.get('date')
    genre = metadata.get('genre') if (overwrite_existing or not curr.get('genre')) else curr.get('genre')

    art_url = metadata.get('art_url')
    art_data = None
    if embed_art and (not has_art or overwrite_existing) and art_url:
        try:
            r = session.get(art_url, timeout=10)
            if r.status_code == 200:
                art_data = r.content
        except Exception as e:
            print(f"  [!] Failed to download artwork from {art_url}: {e}", file=sys.stderr)

    try:
        if ext == '.mp3':
            try:
                audio = EasyID3(filepath)
            except ID3NoHeaderError:
                m = MP3(filepath)
                m.add_tags()
                m.save()
                audio = EasyID3(filepath)

            if title: audio['title'] = title
            if artist: audio['artist'] = artist
            if album: audio['album'] = album
            if date: audio['date'] = str(date)
            if genre: audio['genre'] = genre
            audio.save()

            if art_data:
                id3 = ID3(filepath)
                id3.delall('APIC')
                id3.add(APIC(
                    encoding=3, # UTF-8
                    mime='image/jpeg',
                    type=PictureType.COVER_FRONT,
                    desc='Cover',
                    data=art_data
                ))
                id3.save(v2_version=3)

        elif ext in ('.m4a', '.mp4'):
            mp4 = MP4(filepath)
            if title: mp4['\xa9nam'] = [title]
            if artist: mp4['\xa9ART'] = [artist]
            if album: mp4['\xa9alb'] = [album]
            if date: mp4['\xa9day'] = [str(date)]
            if genre: mp4['\xa9gen'] = [genre]
            if art_data:
                mp4['covr'] = [MP4Cover(art_data, imageformat=MP4Cover.FORMAT_JPEG)]
            mp4.save()

        elif ext == '.flac':
            flac = FLAC(filepath)
            if title: flac['title'] = title
            if artist: flac['artist'] = artist
            if album: flac['album'] = album
            if date: flac['date'] = str(date)
            if genre: flac['genre'] = genre
            if art_data:
                pic = Picture()
                pic.type = 3
                pic.mime = 'image/jpeg'
                pic.desc = 'Cover'
                pic.data = art_data
                flac.clear_pictures()
                flac.add_picture(pic)
            flac.save()

        return True
    except Exception as e:
        print(f"  [!] Error writing tags to '{filepath}': {e}", file=sys.stderr)
        return False


def process_directory(directory: str, dry_run: bool = False, overwrite: bool = False, embed_art: bool = True, rename_hashed: bool = True):
    """Scan and process all music files in a directory."""
    # Sanitize quotes and trailing slashes
    directory = directory.strip('"\'').rstrip('\\/')

    if not os.path.isdir(directory):
        print(f"Error: Directory '{directory}' does not exist.")
        sys.exit(1)

    supported = ('.mp3', '.m4a', '.mp4', '.flac')
    files = [os.path.join(directory, f) for f in sorted(os.listdir(directory)) if os.path.splitext(f)[1].lower() in supported]

    print(f"\n=======================================================")
    print(f" Music Metadata Tagger")
    print(f" Directory: {os.path.abspath(directory)}")
    print(f" Found:     {len(files)} supported audio files")
    print(f" Mode:      {'DRY-RUN (Scan only)' if dry_run else 'APPLY UPDATES'}")
    print(f" Overwrite: {'YES' if overwrite else 'NO (Fill missing only)'}")
    print(f" Embed Art: {'YES' if embed_art else 'NO'}")
    print(f"=======================================================\n")

    if not files:
        print("No supported audio files found.")
        return

    processed = 0
    updated = 0
    art_added = 0

    for idx, path in enumerate(files, 1):
        fn = os.path.basename(path)
        curr = get_current_metadata(path)
        has_art = check_has_artwork(path)
        hashed = is_hashed_filename(fn)

        missing = [k for k, v in curr.items() if not v]
        if not has_art:
            missing.append('artwork')

        print(f"[{idx}/{len(files)}] {fn}")
        if not missing and not overwrite and not hashed:
            print(f"  -> All metadata already present. Skipping.")
            continue

        print(f"  -> Missing: {', '.join(missing) if missing else 'None (Overwrite enabled)'}")

        # Search metadata
        meta = find_best_metadata(path, curr)
        if not meta:
            print(f"  -> No online match found. Skipping.")
            continue

        print(f"  -> Matched: '{meta['title']}' by '{meta['artist']}' | Album: '{meta['album']}' | Year: '{meta['date']}' | Genre: '{meta['genre']}'")
        if not has_art and meta.get('art_url'):
            print(f"  -> Artwork found online and ready to embed.")

        if dry_run:
            processed += 1
            continue

        # Apply tags
        ok = apply_tags(path, meta, overwrite_existing=overwrite, embed_art=embed_art)
        if ok:
            updated += 1
            if not has_art and meta.get('art_url'):
                art_added += 1
            print(f"  -> [SUCCESS] Metadata written successfully.")

            # Auto-rename if filename was a cryptic hash
            if rename_hashed and hashed and meta.get('artist') and meta.get('title'):
                ext = os.path.splitext(path)[1]
                safe_artist = re.sub(r'[\\/*?:"<>|]', '', meta['artist'])
                safe_title = re.sub(r'[\\/*?:"<>|]', '', meta['title'])
                new_fn = f"{safe_artist} - {safe_title}{ext}"
                new_path = os.path.join(directory, new_fn)
                if not os.path.exists(new_path):
                    try:
                        os.rename(path, new_path)
                        print(f"  -> Renamed file to: {new_fn}")
                    except Exception as e:
                        print(f"  -> Could not rename file: {e}")
        
        time.sleep(0.2)

    print(f"\n-------------------------------------------------------")
    if dry_run:
        print(f"Scan complete. {len(files)} files checked.")
    else:
        print(f"Completed! {updated}/{len(files)} files updated.")
        if embed_art:
            print(f"Cover art embedded for {art_added} tracks.")
    print(f"-------------------------------------------------------\n")


def deduplicate_directory(directory: str, dry_run: bool = False):
    """Detect and remove duplicate music files in the directory."""
    import hashlib
    directory = directory.strip('"\'').rstrip('\\/')
    if not os.path.isdir(directory):
        print(f"Error: Directory '{directory}' does not exist.")
        sys.exit(1)

    supported = ('.mp3', '.m4a', '.mp4', '.flac')
    files = sorted([f for f in os.listdir(directory) if os.path.splitext(f)[1].lower() in supported])
    print(f"\n=======================================================")
    print(f" Duplicate Music Cleaner")
    print(f" Directory: {os.path.abspath(directory)}")
    print(f" Files:     {len(files)} audio files")
    print(f" Mode:      {'DRY-RUN (Scan only)' if dry_run else 'REMOVE DUPLICATES'}")
    print(f"=======================================================\n")

    # Hash all files
    by_hash = {}
    file_map = {}
    for f in files:
        full = os.path.join(directory, f)
        h = hashlib.sha256()
        with open(full, 'rb') as fp:
            while chunk := fp.read(65536):
                h.update(chunk)
        sha = h.hexdigest()
        by_hash.setdefault(sha, []).append(f)
        file_map[f] = sha

    to_delete = set()

    # Exact binary duplicates
    for sha, flist in by_hash.items():
        if len(flist) > 1:
            # Keep the shortest/cleanest filename without (1), (2), etc.
            flist_sorted = sorted(flist, key=lambda x: (bool(re.search(r'\([0-9]+\)', x)), len(x)))
            keep = flist_sorted[0]
            for dup in flist_sorted[1:]:
                to_delete.add((dup, f"Exact duplicate of '{keep}'"))

    # Pattern duplicates e.g. "Song (1).mp3" where "Song.mp3" exists
    for f in files:
        m = re.match(r'^(.*?)\s*\(([0-9]+)\)(\.[a-z0-9]+)$', f, re.I)
        if m:
            orig = m.group(1).strip() + m.group(3)
            if orig in files and orig != f:
                to_delete.add((f, f"Numbered duplicate of '{orig}'"))

    if not to_delete:
        print("No duplicate audio files found! Your library is completely clean.\n")
        return

    print(f"Found {len(to_delete)} duplicate files:")
    for fn, reason in sorted(to_delete):
        full = os.path.join(directory, fn)
        size_kb = os.path.getsize(full) / 1024
        print(f"  - {fn} ({size_kb:.1f} KB) -> {reason}")
        if not dry_run:
            try:
                os.remove(full)
                print(f"    [DELETED] Successfully removed {fn}")
            except Exception as e:
                print(f"    [ERROR] Could not delete {fn}: {e}")

    print(f"\nCompleted! {len(to_delete)} duplicates {'found' if dry_run else 'deleted'}.\n")


def main():
    parser = argparse.ArgumentParser(description="Automatically scan and tag music files with missing metadata and artwork.")
    parser.add_argument('directory', nargs='?', default='.', help="Path to music folder (default: current directory)")
    parser.add_argument('--dry-run', action='store_true', help="Scan and show matches without writing changes")
    parser.add_argument('--overwrite', action='store_true', help="Overwrite existing tags with online metadata")
    parser.add_argument('--no-art', action='store_true', help="Skip embedding cover artwork")
    parser.add_argument('--dedup', action='store_true', help="Find and delete duplicate audio copies")

    args = parser.parse_args()
    if args.dedup:
        deduplicate_directory(args.directory, dry_run=args.dry_run)
    else:
        process_directory(args.directory, dry_run=args.dry_run, overwrite=args.overwrite, embed_art=not args.no_art)


if __name__ == '__main__':
    main()
