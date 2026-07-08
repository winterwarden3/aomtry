import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv
import os

load_dotenv()

# Configure Cloudinary
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

def upload_image_to_cloudinary(file, folder="products"):
    """
    Upload image to Cloudinary and return the URL and public_id
    
    Args:
        file: The image file from request.files
        folder: Folder name in Cloudinary (default: 'products')
    
    Returns:
        dict: {'url': secure_url, 'public_id': public_id} or None
    """
    try:
        print(f"📤 Uploading to Cloudinary, folder: {folder}")
        
        # Check if file has content
        if hasattr(file, 'read'):
            file_content = file.read()
            if not file_content:
                print("❌ File is empty (no content)")
                return None
            # Reset file pointer
            file.seek(0)
        
        upload_result = cloudinary.uploader.upload(
            file,
            folder=folder,
            allowed_formats=["jpg", "png", "jpeg", "gif", "webp"],
            transformation=[
                {"width": 800, "height": 600, "crop": "limit"},
                {"quality": "auto"}
            ]
        )
        
        print(f"✅ Upload successful: {upload_result.get('secure_url')}")
        return {
            'url': upload_result.get("secure_url"),
            'public_id': upload_result.get("public_id")
        }
    except Exception as e:
        print(f"❌ Cloudinary upload error: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def delete_image_from_cloudinary(public_id):
    """
    Delete image from Cloudinary
    
    Args:
        public_id: The public ID of the image in Cloudinary
    """
    try:
        if not public_id:
            return False
        result = cloudinary.uploader.destroy(public_id)
        print(f"🗑️ Deleted from Cloudinary: {public_id} - {result.get('result')}")
        return result.get('result') == 'ok'
    except Exception as e:
        print(f"❌ Cloudinary delete error: {str(e)}")
        return False