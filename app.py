# File: app.py

import os
from flask import Flask, render_template, request, jsonify
import requests
import json
import base64
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# --- PayPal API Configuration ---
PAYPAL_CLIENT_ID = os.getenv('PAYPAL_CLIENT_ID')
PAYPAL_CLIENT_SECRET = os.getenv('PAYPAL_CLIENT_SECRET')

# Determine PayPal API base URL based on environment (live vs. sandbox)
PAYPAL_API_BASE = 'https://api-m.sandbox.paypal.com' if os.getenv('FLASK_ENV') != 'production' else 'https://api-m.paypal.com'

# --- Helper Functions for PayPal API Calls ---

def generate_access_token():
    """Generates a PayPal OAuth2.0 Access Token."""
    auth = base64.b64encode(f"{PAYPAL_CLIENT_ID}:{PAYPAL_CLIENT_SECRET}".encode()).decode()
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': f'Basic {auth}'
    }
    data = 'grant_type=client_credentials'
    
    try:
        response = requests.post(f"{PAYPAL_API_BASE}/v1/oauth2/token", headers=headers, data=data)
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        return response.json()['access_token']
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Failed to generate PayPal Access Token: {e}")
        raise

def create_paypal_order(product_details):
    """Creates a new PayPal order."""
    access_token = generate_access_token()
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "amount": {
                "currency_code": product_details['currency'],
                "value": product_details['price'],
                "breakdown": {
                    "item_total": {
                        "currency_code": product_details['currency'],
                        "value": product_details['price']
                    }
                }
            },
            "description": product_details['name'],
            "items": [{
                "name": product_details['name'],
                "description": f"Access to {product_details['name']}",
                "quantity": "1",
                "unit_amount": {
                    "currency_code": product_details['currency'],
                    "value": product_details['price']
                },
                "category": "DIGITAL_GOODS" # Important for digital products
            }]
        }],
        "application_context": {
            "return_url": "https://pay.bugswriter.com/success", # Replace with your actual success URL
            "cancel_url": "https://pay.bugswriter.com/cancel",   # Replace with your actual cancel URL
            "shipping_preference": "NO_SHIPPING" # Crucial for digital goods
        }
    }
    
    try:
        response = requests.post(f"{PAYPAL_API_BASE}/v2/checkout/orders", headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Failed to create PayPal order: {e}. Response: {response.text if 'response' in locals() else 'N/A'}")
        raise

def capture_paypal_order(order_id):
    """Captures an approved PayPal order."""
    access_token = generate_access_token()
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    
    try:
        response = requests.post(f"{PAYPAL_API_BASE}/v2/checkout/orders/{order_id}/capture", headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Failed to capture PayPal order {order_id}: {e}. Response: {response.text if 'response' in locals() else 'N/A'}")
        raise

# --- Flask Routes ---

@app.route('/')
def index():
    """Renders the main checkout page."""
    # You could dynamically pass product details here if needed,
    # but for minimal, we'll keep product details on the frontend JS
    return render_template('index.html', paypal_client_id=PAYPAL_CLIENT_ID)

@app.route('/api/create-paypal-order', methods=['POST'])
def api_create_paypal_order():
    """API endpoint to create a PayPal order."""
    data = request.get_json()
    try:
        order = create_paypal_order(data)
        return jsonify(order)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/capture-paypal-order', methods=['POST'])
def api_capture_paypal_order():
    """API endpoint to capture a PayPal order."""
    data = request.get_json()
    order_id = data.get('orderID')
    if not order_id:
        return jsonify({'error': 'Order ID is required'}), 400
    try:
        capture_response = capture_paypal_order(order_id)
        return jsonify(capture_response)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/paypal-webhook', methods=['POST'])
def paypal_webhook():
    """PayPal Webhook Listener."""
    webhook_event = request.get_json()
    event_type = webhook_event.get('event_type')
    
    app.logger.info(f"Received PayPal Webhook Event: {event_type}")

    # --- IMPORTANT: Webhook Signature Verification ---
    # In a production environment, you MUST verify the webhook signature
    # to ensure the request is genuinely from PayPal and not a malicious actor.
    # This example skips the full verification process for minimalism,
    # but it's CRITICAL for security.
    #
    # How to verify:
    # PayPal provides an API to verify webhook signatures:
    # https://developer.paypal.com/docs/api/webhooks/v1/#webhooks-verify-webhook-signature
    # You would need to extract headers like 'Paypal-Transmission-Id', 'Paypal-Request-Id',
    # 'Paypal-Transmission-Time', 'Paypal-Cert-Url', 'Paypal-Transmission-Sig',
    # 'Paypal-Auth-Algo' and the request body, then send them to PayPal's /v1/notifications/webhooks-event/verify-signature endpoint.
    # Only proceed with processing the event if the verification is successful.
    # ----------------------------------------------------

    if event_type == 'CHECKOUT.ORDER.COMPLETED' or event_type == 'PAYMENT.CAPTURE.COMPLETED':
        order_id = webhook_event['resource']['id']
        payer_email = webhook_event['resource']['payer']['email_address'] if 'payer' in webhook_event['resource'] else 'N/A'
        
        app.logger.info(f"Payment COMPLETED for Order ID: {order_id} by {payer_email}")
        
        # --- Your Content Delivery Logic Here ---
        # 1. Store transaction details in your database (e.g., using Firestore or a simple file for this minimal example)
        # 2. Grant access to the course/video content for `payer_email`
        #    Example: Generate a unique, time-limited access link or add to a private user database.
        # 3. Send a confirmation email with content access instructions.
        #    (You'd use an email sending library/service like SendGrid, Mailgun, etc.)
        
        app.logger.info(f"ACTION: Granting access to content for: {payer_email} for order {order_id}")
        # Example: Simulating content access grant
        # with open('purchased_content_access.log', 'a') as f:
        #     f.write(f"Access granted for {payer_email} to content for order {order_id} at {datetime.now()}\n")
        # send_content_email(payer_email, order_id) # Placeholder for your email function

    elif event_type == 'PAYMENT.REFUND.COMPLETED':
        order_id = webhook_event['resource']['id']
        refund_amount = webhook_event['resource']['amount']['value']
        refund_currency = webhook_event['resource']['amount']['currency_code']
        app.logger.info(f"Payment REFUNDED for Order ID: {order_id}, Amount: {refund_amount} {refund_currency}")
        # --- Your Refund Handling Logic Here ---
        # 1. Revoke access to content if applicable
        # 2. Update your internal records (e.g., mark as refunded)

    # Always return a 200 OK to PayPal to acknowledge receipt of the webhook
    return jsonify({'status': 'success'}), 200

# Simple success and cancel pages (optional, can be redirected from frontend JS)
@app.route('/success')
def success_page():
    return "<h1>Payment Success!</h1><p>Thank you for your purchase. Your content access will be delivered shortly.</p>"

@app.route('/cancel')
def cancel_page():
    return "<h1>Payment Cancelled</h1><p>You have cancelled the payment. No charges were made.</p>"

if __name__ == '__main__':
    # For local development:
    # Ensure FLASK_ENV is set to 'development' in your .env or shell
    # Set your host to '0.0.0.0' to be accessible from outside localhost if needed
    app.run(debug=True, host='0.0.0.0', port=5000)
