import cloudinary
import cloudinary.uploader
import cloudinary.api
from typing import Optional, BinaryIO
from fastapi import UploadFile
import io
from libdata.settings import settings

# Configure Cloudinary
cloudinary.config(
    cloud_name=settings.cloudinary_cloud_name,
    api_key=settings.cloudinary_api_key,
    api_secret=settings.cloudinary_api_secret,
    secure=True
)


class CloudinaryService:
    """Service for handling image uploads to Cloudinary"""
    
    @staticmethod
    def upload_image(
        file: UploadFile,
        folder: str = "vehicle-damage",
        public_id: Optional[str] = None,
        transformation: Optional[dict] = None
    ) -> dict:
        """
        Upload an image to Cloudinary
        
        Args:
            file: The uploaded file
            folder: Cloudinary folder to store the image
            public_id: Optional custom public ID for the image
            transformation: Optional transformation parameters
            
        Returns:
            dict with url, secure_url, public_id, and other Cloudinary response data
        """
        try:
            # Read file content
            file_content = file.file.read()
            
            # Reset file pointer
            file.file.seek(0)
            
            # Upload to Cloudinary
            upload_params = {
                "folder": folder,
                "resource_type": "auto",
                "format": "jpg",  # Convert to JPG for consistency
                "quality": "auto:good",  # Automatic quality optimization
            }
            
            if public_id:
                upload_params["public_id"] = public_id
            
            if transformation:
                upload_params["transformation"] = transformation
            
            result = cloudinary.uploader.upload(
                file_content,
                **upload_params
            )
            
            return {
                "url": result.get("url"),
                "secure_url": result.get("secure_url"),
                "public_id": result.get("public_id"),
                "format": result.get("format"),
                "resource_type": result.get("resource_type"),
                "width": result.get("width"),
                "height": result.get("height"),
                "bytes": result.get("bytes"),
                "created_at": result.get("created_at"),
            }
            
        except Exception as e:
            raise Exception(f"Error uploading to Cloudinary: {str(e)}")
    
    @staticmethod
    def upload_multiple_images(
        files: list[UploadFile],
        folder: str = "vehicle-damage",
        claim_id: Optional[int] = None
    ) -> list[dict]:
        """
        Upload multiple images to Cloudinary
        
        Args:
            files: List of uploaded files
            folder: Cloudinary folder to store the images
            claim_id: Optional claim ID to organize images
            
        Returns:
            List of dicts with image URLs and metadata
        """
        uploaded_images = []
        
        for i, file in enumerate(files):
            try:
                # Create a folder structure: vehicle-damage/claim_123/
                file_folder = f"{folder}/claim_{claim_id}" if claim_id else folder
                
                # Upload the image
                result = CloudinaryService.upload_image(
                    file=file,
                    folder=file_folder,
                    public_id=None  # Let Cloudinary generate unique ID
                )
                
                uploaded_images.append({
                    "file_path": result["secure_url"],
                    "original_filename": file.filename,
                    "cloudinary_public_id": result["public_id"],
                    "width": result.get("width"),
                    "height": result.get("height"),
                    "format": result.get("format"),
                })
                
            except Exception as e:
                print(f"Error uploading {file.filename}: {str(e)}")
                # Continue with other files even if one fails
                continue
        
        return uploaded_images
    
    @staticmethod
    def delete_image(public_id: str) -> bool:
        """
        Delete an image from Cloudinary
        
        Args:
            public_id: The Cloudinary public ID of the image
            
        Returns:
            True if successful, False otherwise
        """
        try:
            result = cloudinary.uploader.destroy(public_id)
            return result.get("result") == "ok"
        except Exception as e:
            print(f"Error deleting image {public_id}: {str(e)}")
            return False


# Create a singleton instance
cloudinary_service = CloudinaryService()
