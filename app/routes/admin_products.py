from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
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
    """Add new product with image upload - AJAX ready"""
    
    # Check if AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        price = request.form.get('price')
        category = request.form.get('category')
        image = request.files.get('image')
        
        # Validation
        if not name:
            if is_ajax:
                return jsonify({'success': False, 'error': 'Product name is required'}), 400
            flash('Product name is required', 'danger')
            return redirect(url_for('admin_products.add_product'))
        
        # Upload image to Cloudinary if provided
        image_url = None
        if image and image.filename:
            image_url = upload_image_to_cloudinary(image)
            if not image_url:
                if is_ajax:
                    return jsonify({'success': False, 'error': 'Failed to upload image'}), 500
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
            if is_ajax:
                return jsonify({
                    'success': True,
                    'message': f'Product "{name}" added successfully!',
                    'redirect': url_for('admin_products.product_list')
                })
            flash('Product added successfully!', 'success')
            return redirect(url_for('admin_products.product_list'))
        else:
            if is_ajax:
                return jsonify({'success': False, 'error': 'Failed to add product'}), 500
            flash('Failed to add product', 'danger')
    
    return render_template('admin/add_product.html')


@bp.route('/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_product(product_id):
    """Edit existing product - AJAX ready"""
    
    product = Product.get_by_id(product_id)
    if not product:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'Product not found'}), 404
        flash('Product not found', 'danger')
        return redirect(url_for('admin_products.product_list'))
    
    # Check if AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
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
                try:
                    # Extract public_id from URL
                    public_id = product['image_url'].split('/')[-1].split('.')[0]
                    delete_image_from_cloudinary(f"products/{public_id}")
                except Exception as e:
                    print(f"Error deleting old image: {e}")
            
            # Upload new image
            image_url = upload_image_to_cloudinary(image)
            if image_url:
                update_data['image_url'] = image_url
            else:
                if is_ajax:
                    return jsonify({'success': False, 'error': 'Failed to upload image'}), 500
                flash('Failed to upload image', 'danger')
                return redirect(url_for('admin_products.edit_product', product_id=product_id))
        
        result = Product.update(product_id, update_data)
        
        if result:
            if is_ajax:
                return jsonify({
                    'success': True,
                    'message': f'Product "{name}" updated successfully!',
                    'redirect': url_for('admin_products.product_list')
                })
            flash('Product updated successfully!', 'success')
            return redirect(url_for('admin_products.product_list'))
        else:
            if is_ajax:
                return jsonify({'success': False, 'error': 'Failed to update product'}), 500
            flash('Failed to update product', 'danger')
    
    return render_template('admin/edit_product.html', product=product)


@bp.route('/delete/<int:product_id>', methods=['POST'])
@login_required
@admin_required
def delete_product(product_id):
    """Delete product - AJAX ready"""
    
    # Check if AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    try:
        product = Product.get_by_id(product_id)
        
        if not product:
            if is_ajax:
                return jsonify({'success': False, 'error': 'Product not found'}), 404
            flash('Product not found', 'danger')
            return redirect(url_for('admin_products.product_list'))
        
        product_name = product.get('name')
        
        # Delete image from Cloudinary if exists
        if product.get('image_url'):
            try:
                # Extract public_id from URL
                image_url = product['image_url']
                # Handle different Cloudinary URL formats
                if '/upload/' in image_url:
                    parts = image_url.split('/upload/')
                    if len(parts) > 1:
                        path_parts = parts[1].split('/')
                        if len(path_parts) > 1:
                            public_id = '/'.join(path_parts[1:]).split('.')[0]
                        else:
                            public_id = path_parts[0].split('.')[0]
                    else:
                        public_id = image_url.split('/')[-1].split('.')[0]
                else:
                    public_id = image_url.split('/')[-1].split('.')[0]
                
                delete_image_from_cloudinary(f"products/{public_id}")
                print(f"Deleted image: products/{public_id}")
            except Exception as e:
                print(f"Error deleting image from Cloudinary: {e}")
                # Continue with product deletion even if image deletion fails
        
        # Delete from Supabase
        result = Product.delete(product_id)
        
        if result:
            if is_ajax:
                return jsonify({
                    'success': True,
                    'message': f'Product "{product_name}" deleted successfully!'
                })
            flash('Product deleted successfully!', 'success')
        else:
            if is_ajax:
                return jsonify({'success': False, 'error': 'Failed to delete product'}), 500
            flash('Failed to delete product', 'danger')
            
    except Exception as e:
        print(f"Error deleting product: {e}")
        if is_ajax:
            return jsonify({'success': False, 'error': str(e)}), 500
        flash(f'Error deleting product: {str(e)}', 'danger')
    
    if not is_ajax:
        return redirect(url_for('admin_products.product_list'))
    return jsonify({'success': True})