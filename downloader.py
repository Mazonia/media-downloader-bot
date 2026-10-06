"""
Media Downloader Engine powered by yt-dlp.
Supports dynamic multi-resolution ladder: 480p, 720p, 1080p, 1440p (2K), 2160p (4K), 4320p (8K).
"""

import os
import uuid
import glob
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from loguru import logger
import yt_dlp

import config


class MediaDownloader:
    """Extracts resolution ladder and downloads at the user-selected resolution."""

    @staticmethod
    def get_info_and_resolutions(url: str) -> Optional[Dict[str, Any]]:
        """Extract metadata and list all available resolutions from 480p up to maximum."""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    return None

                # Find all available heights with video codecs
                raw_heights = set()
                for f in info.get("formats", []):
                    h = f.get("height")
                    vcodec = f.get("vcodec", "")
                    if h and isinstance(h, int) and vcodec != "none" and vcodec != "":
                        raw_heights.add(h)

                max_h = max(raw_heights) if raw_heights else 720

                # Build resolution ladder starting from 480p up to max
                candidate_ladder = [
                    (480, "480p (SD)"),
                    (720, "720p (HD)"),
                    (1080, "1080p (Full HD)"),
                    (1440, "1440p (2K QHD)"),
                    (2160, "4K UHD (2160p)"),
                    (4320, "8K UHD (4320p)"),
                ]

                # Filter resolutions that are available or up to the max height
                available_options = []
                for res_val, res_label in candidate_ladder:
                    if res_val <= max_h:
                        available_options.append({"height": res_val, "label": res_label})

                # If video has unusual resolution (e.g. 1088 or 1600), ensure max is represented
                if not available_options or available_options[-1]["height"] < max_h:
                    available_options.append({"height": max_h, "label": f"{max_h}p (Max Source)"})

                # Ensure at least 480p is available
                if not available_options:
                    available_options = [{"height": 720, "label": "720p HD"}]

                return {
                    "title": info.get("title", "Video"),
                    "duration": info.get("duration", 0),
                    "uploader": info.get("uploader") or info.get("channel") or "Unknown",
                    "thumbnail": info.get("thumbnail"),
                    "max_height": max_h,
                    "resolutions": available_options,
                }
        except Exception as e:
            logger.error(f"Error extracting info for {url}: {e}")
            return None

    @staticmethod
    def download_video_at_resolution(url: str, target_height: int) -> Tuple[Optional[Path], str, int]:
        """
        Download video at selected target height (e.g. 480, 720, 1080, 2160, 4320).
        Returns: (file_path, title, file_size_mb)
        """
        file_id = uuid.uuid4().hex[:8]
        out_tmpl = str(config.DOWNLOAD_DIR / f"vid_{file_id}.%(ext)s")

        fmt = f"bestvideo[height<={target_height}]+bestaudio/best[height<={target_height}]/best"

        ydl_opts = {
            'format': fmt,
            'outtmpl': out_tmpl,
            'quiet': True,
            'no_warnings': True,
            'merge_output_format': 'mp4',
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get("title", "Video") if info else "Video"

            matches = glob.glob(str(config.DOWNLOAD_DIR / f"vid_{file_id}.*"))
            if matches:
                p = Path(matches[0])
                size_mb = int(p.stat().st_size / (1024 * 1024))
                return p, title, size_mb
            return None, "File not found after download.", 0
        except Exception as e:
            err = str(e)
            logger.error(f"Download failed for {url}: {err}")
            return None, f"Download error: {err[:120]}", 0

    @staticmethod
    def download_audio(url: str) -> Tuple[Optional[Path], str, int]:
        """Download and extract audio as high-bitrate MP3 (320kbps)."""
        file_id = uuid.uuid4().hex[:8]
        out_tmpl = str(config.DOWNLOAD_DIR / f"aud_{file_id}.%(ext)s")

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': out_tmpl,
            'quiet': True,
            'no_warnings': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }],
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get("title", "Audio") if info else "Audio"

            matches = glob.glob(str(config.DOWNLOAD_DIR / f"aud_{file_id}.*"))
            if matches:
                p = Path(matches[0])
                size_mb = int(p.stat().st_size / (1024 * 1024))
                return p, title, size_mb
            return None, "Audio file not found.", 0
        except Exception as e:
            logger.error(f"Audio extraction failed for {url}: {e}")
            return None, f"Extraction error: {str(e)[:120]}", 0
