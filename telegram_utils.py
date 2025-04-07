"""
Telegram Chunked File Storage Utility for VideoVault

This module provides functionality to upload large files to Telegram in chunks
and download them back, enabling VideoVault to use Telegram as a storage backend.
"""

import os
import math
import json
import logging
import asyncio
import tempfile
from typing import List, Dict, Any, Tuple, Optional
from tqdm import tqdm

# Configure logger
logger = logging.getLogger('telegram_utils')
logging.basicConfig(level=logging.INFO)

# Constants
MAX_CHUNK_SIZE = 1.9 * 1024 * 1024 * 1024  # 1.9GB in bytes
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.environ.get('TELEGRAM_CHANNEL_ID')

# Check if essential environment variables are available
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
    logger.error("Missing Telegram bot token or channel ID. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID in .env file.")

# Import telegram libraries after checking tokens
try:
    from telegram import Bot
    from telegram.error import TelegramError
except ImportError:
    logger.error("Failed to import python-telegram-bot. Make sure it's installed.")
    raise

class TelegramStorage:
    """
    Class to handle chunked file storage and retrieval using Telegram.
    """
    
    def __init__(self, bot_token=None, channel_id=None):
        """
        Initialize with bot token and channel ID.
        """
        self.bot_token = bot_token or TELEGRAM_BOT_TOKEN
        self.channel_id = channel_id or TELEGRAM_CHANNEL_ID
        self.temp_dir = tempfile.gettempdir()
        self.bot = Bot(token=self.bot_token)
        
    async def _upload_chunk(self, chunk_path: str, chunk_number: int, custom_caption: str = None) -> str:
        """
        Upload a single chunk to Telegram and return the file_id.
        
        Args:
            chunk_path: Path to the chunk file
            chunk_number: Chunk sequence number
            custom_caption: Optional caption to add to the first chunk
        """
        # Only use custom caption for the first chunk
        caption = custom_caption if chunk_number == 0 and custom_caption else f"Chunk {chunk_number}"
        
        try:
            with open(chunk_path, 'rb') as chunk_file:
                message = await self.bot.send_document(
                    chat_id=self.channel_id, 
                    document=chunk_file,
                    caption=caption,
                    filename=f"chunk_{chunk_number}.bin"
                )
                # Get the file_id of the uploaded document
                if message.document:
                    return message.document.file_id
                else:
                    raise ValueError("Failed to get file_id from uploaded document")
        except TelegramError as e:
            logger.error(f"Telegram error uploading chunk {chunk_number}: {e}")
            raise
            
    async def upload_file(self, file_path: str, custom_caption: str = None) -> Dict[str, Any]:
        """
        Split a file into chunks and upload them to Telegram.
        Returns metadata about the uploaded chunks.
        
        Args:
            file_path: Path to the file to upload
            custom_caption: Optional caption to add to the first chunk
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
            
        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)
        
        # Calculate number of chunks needed
        num_chunks = math.ceil(file_size / MAX_CHUNK_SIZE)
        logger.info(f"File size: {file_size} bytes, will be split into {num_chunks} chunks")
        
        chunks_metadata = {
            "original_filename": file_name,
            "original_size": file_size,
            "chunks": num_chunks,
            "chunk_file_ids": [],
        }
        
        try:
            with open(file_path, 'rb') as file:
                for chunk_number in tqdm(range(num_chunks), desc="Uploading chunks"):
                    # Create a temporary file for this chunk
                    chunk_path = os.path.join(self.temp_dir, f"chunk_{chunk_number}.bin")
                    
                    # Read chunk data
                    chunk_data = file.read(int(MAX_CHUNK_SIZE))
                    
                    # Write chunk to temporary file
                    with open(chunk_path, 'wb') as chunk_file:
                        chunk_file.write(chunk_data)
                    
                    # Upload chunk and get file_id, pass caption only for first chunk
                    file_id = await self._upload_chunk(
                        chunk_path, 
                        chunk_number, 
                        custom_caption if chunk_number == 0 else None
                    )
                    chunks_metadata["chunk_file_ids"].append(file_id)
                    
                    # Clean up temporary chunk file
                    os.unlink(chunk_path)
                    
            return chunks_metadata
            
        except Exception as e:
            logger.error(f"Error during file upload: {e}")
            raise
            
    async def _download_chunk(self, file_id: str, output_path: str) -> None:
        """
        Download a single chunk from Telegram by file_id.
        """
        try:
            file = await self.bot.get_file(file_id)
            await file.download_to_drive(output_path)
        except TelegramError as e:
            logger.error(f"Error downloading chunk with file_id {file_id}: {e}")
            raise
            
    async def download_file(self, chunk_file_ids: List[str], output_path: str) -> str:
        """
        Download chunks from Telegram and merge them into the original file.
        Returns the path to the merged file.
        """
        if not chunk_file_ids:
            raise ValueError("No chunk file IDs provided")
            
        try:
            # Create temporary directory for chunks
            temp_chunk_dir = tempfile.mkdtemp()
            
            # Download all chunks
            chunk_paths = []
            for i, file_id in enumerate(tqdm(chunk_file_ids, desc="Downloading chunks")):
                chunk_path = os.path.join(temp_chunk_dir, f"chunk_{i}.bin")
                await self._download_chunk(file_id, chunk_path)
                chunk_paths.append(chunk_path)
                
            # Merge chunks into final file
            with open(output_path, 'wb') as output_file:
                for chunk_path in tqdm(chunk_paths, desc="Merging chunks"):
                    with open(chunk_path, 'rb') as chunk_file:
                        output_file.write(chunk_file.read())
                        
            # Clean up temporary chunks
            for chunk_path in chunk_paths:
                os.unlink(chunk_path)
            os.rmdir(temp_chunk_dir)
            
            return output_path
            
        except Exception as e:
            logger.error(f"Error during file download: {e}")
            raise

# Helper functions for synchronous operation in Flask
def upload_file_sync(file_path: str, custom_caption: str = None) -> Dict[str, Any]:
    """
    Synchronous wrapper for upload_file.
    
    Args:
        file_path: Path to the file to upload
        custom_caption: Optional caption to add to the first chunk
    """
    storage = TelegramStorage()
    return asyncio.run(storage.upload_file(file_path, custom_caption))
    
def download_file_sync(chunk_file_ids: List[str], output_path: str) -> str:
    """
    Synchronous wrapper for download_file.
    """
    storage = TelegramStorage()
    return asyncio.run(storage.download_file(chunk_file_ids, output_path))