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
    Upload image to Cloudinary and return the URL
    
    Args:
        file: The image file from request.files
        folder: Folder name in Cloudinary (default: 'products')
    
    Returns:
        string: Cloudinary URL of uploaded image
    """
    try:
        upload_result = cloudinary.uploader.upload(
            file,
            folder=folder,
            allowed_formats=["jpg", "png", "jpeg", "gif"],
            transformation=[
                {"width": 500, "height": 500, "crop": "limit"},
                {"quality": "auto"}
            ]
        )
        return upload_result.get("secure_url")
    except Exception as e:
        print(f"❌ Cloudinary upload error: {str(e)}")
        return None

def delete_image_from_cloudinary(public_id):
    """
    Delete image from Cloudinary
    
    Args:
        public_id: The public ID of the image in Cloudinary
    """
    try:
        cloudinary.uploader.destroy(public_id)
        return True
    except Exception as e:
        print(f"❌ Cloudinary delete error: {str(e)}")
        return False