"""
Media Downloader Engine powered by yt-dlp.
Supports dynamic multi-resolution ladder: 480p, 720p, 1080p, 1440p (2K), 2160p (4K), 4320p (8K).
Includes smart pre-download size estimation and chunk splitter for Telegram delivery.
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
    """Extracts resolution ladder, estimates filesize before downloading, and downloads."""

    @staticmethod
    def _fallback_bitrate_kbps(height: int) -> int:
        """Approximate average combined bitrate (video+audio) in kbps for given vertical resolution."""
        if height <= 480:
            return 1000
        elif height <= 720:
            return 2600
        elif height <= 1080:
            return 5200
        elif height <= 1440:
            return 10500
        elif height <= 2160:
            return 25000
        else:
            return 60000

    @classmethod
    def estimate_video_size_mb(cls, info: Dict[str, Any], target_height: int) -> int:
        """Estimate file size in MB for target resolution BEFORE downloading."""
        formats = info.get("formats", [])
        duration = info.get("duration") or 0

        # Find best video stream <= target_height
        v_candidates = [
            f for f in formats 
            if f.get("vcodec") and f.get("vcodec") != "none" and f.get("height") and f["height"] <= target_height
        ]
        if not v_candidates:
            v_candidates = [f for f in formats if f.get("vcodec") and f.get("vcodec") != "none"]

        if not v_candidates:
            br = cls._fallback_bitrate_kbps(target_height)
            dur_sec = duration if duration > 0 else 180
            return max(1, int((br * 1000 / 8 * dur_sec) / (1024 * 1024)))

        best_v = max(v_candidates, key=lambda f: (f.get("height") or 0, f.get("tbr") or f.get("vbr") or 0))
        v_bytes = best_v.get("filesize") or best_v.get("filesize_approx")

        if not v_bytes and duration > 0:
            v_bitrate = best_v.get("vbr") or best_v.get("tbr") or cls._fallback_bitrate_kbps(target_height)
            v_bytes = (v_bitrate * 1000 / 8) * duration
        elif not v_bytes:
            default_mb = {480: 30, 720: 70, 1080: 160, 1440: 350, 2160: 850, 4320: 2000}.get(target_height, 80)
            v_bytes = default_mb * 1024 * 1024

        # If best_v is already combined (has audio)
        if best_v.get("acodec") and best_v.get("acodec") != "none":
            return max(1, int(v_bytes / (1024 * 1024)))

        # Find audio format
        a_candidates = [
            f for f in formats 
            if f.get("acodec") and f.get("acodec") != "none" and (not f.get("vcodec") or f.get("vcodec") == "none")
        ]
        a_bytes = 0
        if a_candidates:
            best_a = max(a_candidates, key=lambda f: f.get("abr") or f.get("tbr") or 0)
            a_bytes = best_a.get("filesize") or best_a.get("filesize_approx") or 0
            if not a_bytes and duration > 0:
                a_bitrate = best_a.get("abr") or 128
                a_bytes = (a_bitrate * 1000 / 8) * duration
            elif not a_bytes:
                a_bytes = 10 * 1024 * 1024

        total_bytes = v_bytes + a_bytes
        return max(1, int(total_bytes / (1024 * 1024)))

    @classmethod
    def estimate_audio_size_mb(cls, info: Dict[str, Any]) -> int:
        """Estimate MP3 audio size in MB BEFORE downloading."""
        duration = info.get("duration") or 0
        formats = info.get("formats", [])
        a_candidates = [
            f for f in formats 
            if f.get("acodec") and f.get("acodec") != "none" and (not f.get("vcodec") or f.get("vcodec") == "none")
        ]
        if a_candidates:
            best_a = max(a_candidates, key=lambda f: f.get("abr") or f.get("tbr") or 0)
            sz = best_a.get("filesize") or best_a.get("filesize_approx")
            if sz:
                return max(1, int(sz / (1024 * 1024)))

        if duration > 0:
            return max(1, int((320 * 1000 / 8 * duration) / (1024 * 1024)))
        return 12

    @classmethod
    def get_info_and_resolutions(cls, url: str) -> Optional[Dict[str, Any]]:
        """Extract metadata, estimate sizes, and list all available resolutions."""
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

                raw_heights = set()
                for f in info.get("formats", []):
                    h = f.get("height")
                    vcodec = f.get("vcodec", "")
                    if h and isinstance(h, int) and vcodec != "none" and vcodec != "":
                        raw_heights.add(h)

                max_h = max(raw_heights) if raw_heights else 720

                candidate_ladder = [
                    (480, "480p (SD)"),
                    (720, "720p (HD)"),
                    (1080, "1080p (Full HD)"),
                    (1440, "1440p (2K QHD)"),
                    (2160, "4K UHD (2160p)"),
                    (4320, "8K UHD (4320p)"),
                ]

                available_options = []
                for res_val, res_label in candidate_ladder:
                    if res_val <= max_h:
                        est_mb = cls.estimate_video_size_mb(info, res_val)
                        available_options.append({
                            "height": res_val,
                            "label": res_label,
                            "est_mb": est_mb,
                        })

                if not available_options or available_options[-1]["height"] < max_h:
                    est_mb = cls.estimate_video_size_mb(info, max_h)
                    available_options.append({
                        "height": max_h,
                        "label": f"{max_h}p (Max Source)",
                        "est_mb": est_mb,
                    })

                if not available_options:
                    available_options = [{"height": 720, "label": "720p HD", "est_mb": 50}]

                audio_est_mb = cls.estimate_audio_size_mb(info)

                return {
                    "title": info.get("title", "Video"),
                    "duration": info.get("duration", 0),
                    "uploader": info.get("uploader") or info.get("channel") or "Unknown",
                    "thumbnail": info.get("thumbnail"),
                    "max_height": max_h,
                    "resolutions": available_options,
                    "audio_est_mb": audio_est_mb,
                }
        except Exception as e:
            logger.error(f"Error extracting info for {url}: {e}")
            return None

    @staticmethod
    def download_video_at_resolution(url: str, target_height: int) -> Tuple[Optional[Path], str, int]:
        """Download video at selected target height."""
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

    @staticmethod
    def split_file_for_telegram(file_path: Path, max_part_size_mb: int = 48) -> List[Path]:
        """Split any file larger than 50MB into clean parts for Telegram delivery."""
        part_size_bytes = max_part_size_mb * 1024 * 1024
        total_size = file_path.stat().st_size
        if total_size <= part_size_bytes:
            return [file_path]

        parts = []
        base_name = file_path.name
        part_num = 1
        with open(file_path, "rb") as f_in:
            while True:
                chunk = f_in.read(part_size_bytes)
                if not chunk:
                    break
                part_path = file_path.parent / f"{base_name}.part{part_num}"
                with open(part_path, "wb") as f_out:
                    f_out.write(chunk)
                parts.append(part_path)
                part_num += 1
        return parts
