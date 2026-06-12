from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.utils import admin_required
from app.models_supabase import Product
from app.cloudinary_client import upload_image_to_cloudinary, delete_image_from_cloudinary
import cloudinary

bp = Blueprint('admin_products', __name__, url_prefix='/admin/products')



@bp.route('/')
@login_required
@admin_required
def product_list():
    """List all products"""
    products = Product.get_all()
    return render_template('admin/products.html', products=products)

@bp.route('/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_product():
    """Add new product with image upload"""
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        price = request.form.get('price')
        category = request.form.get('category')
        image = request.files.get('image')
        
        # Validation
        if not name:
            flash('Product name is required', 'danger')
            return redirect(url_for('admin_products.add_product'))
        
        # Upload image to Cloudinary if provided
        image_url = None
        if image and image.filename:
            image_url = upload_image_to_cloudinary(image)
            if not image_url:
                flash('Failed to upload image', 'danger')
                return redirect(url_for('admin_products.add_product'))
        
        # Create product in Supabase
        product_data = {
            'name': name,
            'description': description,
            'price': float(price) if price else None,
            'category': category,
            'image_url': image_url
        }
        
        result = Product.create(product_data)
        
        if result:
            flash('Product added successfully!', 'success')
            return redirect(url_for('admin_products.product_list'))
        else:
            flash('Failed to add product', 'danger')
    
    return render_template('admin/add_product.html')

@bp.route('/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_product(product_id):
    """Edit existing product"""
    
    product = Product.get_by_id(product_id)
    if not product:
        flash('Product not found', 'danger')
        return redirect(url_for('admin_products.product_list'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        price = request.form.get('price')
        category = request.form.get('category')
        image = request.files.get('image')
        
        # Prepare update data
        update_data = {
            'name': name,
            'description': description,
            'price': float(price) if price else None,
            'category': category
        }
        
        # Upload new image if provided
        if image and image.filename:
            # Delete old image from Cloudinary if exists
            if product.get('image_url'):
                # Extract public_id from URL
                public_id = product['image_url'].split('/')[-1].split('.')[0]
                delete_image_from_cloudinary(f"products/{public_id}")
            
            # Upload new image
            image_url = upload_image_to_cloudinary(image)
            if image_url:
                update_data['image_url'] = image_url
        
        result = Product.update(product_id, update_data)
        
        if result:
            flash('Product updated successfully!', 'success')
            return redirect(url_for('admin_products.product_list'))
        else:
            flash('Failed to update product', 'danger')
    
    return render_template('admin/edit_product.html', product=product)

@bp.route('/delete/<int:product_id>', methods=['POST'])
@login_required
@admin_required
def delete_product(product_id):
    """Delete product"""
    
    product = Product.get_by_id(product_id)
    
    if product:
        # Delete image from Cloudinary if exists
        if product.get('image_url'):
            public_id = product['image_url'].split('/')[-1].split('.')[0]
            delete_image_from_cloudinary(f"products/{public_id}")
        
        # Delete from Supabase
        Product.delete(product_id)
        flash('Product deleted successfully!', 'success')
    else:
        flash('Product not found', 'danger')
    
    return redirect(url_for('admin_products.product_list'))