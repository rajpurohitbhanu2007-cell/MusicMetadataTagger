# Music Metadata Tagger

A Python tool that scans your music collection, detects missing audio tags (Title, Artist, Album, Year, Genre, Cover Art), queries online music databases, and writes standard tags directly into your audio files.

---

## 🎯 Approach & Architecture

### 1. Tag Inspection
The script inspects existing audio metadata using [Mutagen](https://mutagen.readthedocs.io/):
- **MP3**: Reads ID3v2 frames (`TIT2`, `TPE1`, `TALB`, `TYER`/`TDRC`, `TCON`, `APIC`).
- **M4A / AAC**: Reads MP4 atom boxes (`©nam`, `©ART`, `©alb`, `©day`, `©gen`, `covr`).
- **FLAC**: Reads Vorbis comments and FLAC picture blocks.

It determines exactly which fields are missing (e.g., missing album, year, genre, or album art).

### 2. Smart Query Cleansing
Filenames often carry video or download baggage (e.g., `(Official Video)`, `[Lyrics]`, `(feat. XYZ)`, `_`, etc.).
The tool sanitizes this noise into clean search queries:
```
"Billie_Eilish_What_Was_I_Made_For_From_The_Motion_Picture_Bar.mp3"
  └──> Sanitized Query: "Billie Eilish What Was I Made For"
```

### 3. Database Matching (iTunes Search API)
- Queries the iTunes Search API using `entity=song` to obtain canonical releases.
- No API keys or authentication required.
- Includes automatic session retries and rate-limiting safeguards.
- Extracts canonical metadata:
  - **Title** (`trackName`)
  - **Artist** (`artistName`)
  - **Album** (`collectionName`)
  - **Year** (`releaseDate`)
  - **Genre** (`primaryGenreName`)
  - **Artwork** (`artworkUrl100` dynamically upgraded to `600x600` or higher)

### 4. Non-Destructive Tagging
By default, existing valid tags and existing cover artwork are **preserved**. Only missing fields are populated. If you want to refresh all tags completely, use the `--overwrite` flag.

---

## 🚀 Installation

Ensure Python 3.8+ is installed, then install the dependencies:

```bash
pip install -r requirements.txt
```

*(Dependencies: `mutagen`, `requests`, `urllib3`)*

---

## 💻 Usage

### 1. Scan / Preview Mode (`--dry-run`)
Checks files and shows what metadata would be updated without writing anything to disk:
```bash
python tagger.py "C:\Music\EnglishMusic" --dry-run
```

### 2. Apply Updates (Fill Missing Tags & Artwork)
Scans the folder, fills missing tags, and embeds cover art if missing:
```bash
python tagger.py "C:\Music\EnglishMusic"
```

### 3. Overwrite Existing Tags
Replaces all existing tags with the canonical online metadata:
```bash
python tagger.py "C:\Music\EnglishMusic" --overwrite
```

### 4. Skip Artwork Embedding
If you only want text metadata without fetching cover pictures:
```bash
python tagger.py "C:\Music\EnglishMusic" --no-art
```

---

## 📁 Project Structure

```
MusicMetadataTagger/
├── Launch_Tagger.bat   # Interactive Windows Menu & Drag-and-Drop Launcher
├── tagger.py           # Core CLI application
├── requirements.txt    # Project dependencies
└── README.md           # Documentation and usage guide
```

---

## ⚡ Manual Launchers

Two launchers are available for 1-click execution:

1. **Inside the Music Folder (`C:\Users\rajpu\Music\EnglishMusic\Tag_Music.bat`)**:
   - Double-click to instantly scan for any newly added music files and fill missing metadata & artwork.

2. **Main Interactive Launcher (`C:\CodeDirectory\CODES\MusicMetadataTagger\Launch_Tagger.bat`)**:
   - Provides an interactive menu with options:
     - `[1]` Scan and fill missing metadata in default music folder
     - `[2]` Dry-run preview without modifying files
     - `[3]` Overwrite and refresh entire collection
     - `[4]` Tag any custom folder (type path or drag-and-drop a folder onto the `.bat` file)

