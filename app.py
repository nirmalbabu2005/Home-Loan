from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import timedelta
import os
import random
import time

app = Flask(__name__)
app.secret_key = "smart_choice_super_secret"
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

db = SQLAlchemy(app)

# --- DATABASE MODELS ---
class Partner(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    password = db.Column(db.String(200), nullable=False)
    dsa_code = db.Column(db.String(20), unique=True, nullable=False)
    leads = db.relationship('Lead', backref='partner', lazy=True)

class Lead(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=True) 
    password = db.Column(db.String(200), nullable=True) 
    product = db.Column(db.String(50), nullable=False, default="Home Purchase")
    amount = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(20), default="Pending")
    partner_id = db.Column(db.Integer, db.ForeignKey('partner.id'), nullable=True) 
    
    # KYC Tracking
    aadhaar_uploaded = db.Column(db.Boolean, default=False)
    pan_uploaded = db.Column(db.Boolean, default=False)
    bank_uploaded = db.Column(db.Boolean, default=False)
    
    # 🟢 NEW: AI & FINANCIAL DATA 🟢
    monthly_income = db.Column(db.Integer, default=0)
    emp_type = db.Column(db.String(50), default="Salaried")
    cibil_score = db.Column(db.Integer, default=0)
    ai_remarks = db.Column(db.String(200), default="")

with app.app_context():
    db.create_all()

def format_currency(val):
    if val >= 10000000: return f"₹ {val/10000000:.2f} Cr"
    elif val >= 100000: return f"₹ {val/100000:.2f} L"
    elif val == 0: return "Amount TBD"
    else: return f"₹ {val:,.0f}"

@app.context_processor
def inject_user_status():
    user_status = {'logged_in': False, 'dashboard': '/login.html'}
    if 'partner_id' in session:
        user_status = {'logged_in': True, 'type': 'Partner', 'dashboard': '/partner-dashboard.html'}
    elif 'customer_lead_id' in session:
        user_status = {'logged_in': True, 'type': 'Customer', 'dashboard': '/customer-dashboard.html'}
    return dict(user_status=user_status)

# ==========================================
# 🚀 API ROUTES 
# ==========================================
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    login_id = data.get('login_id')
    password = data.get('password')
    login_type = data.get('type')

    if login_type == 'Partner':
        user = Partner.query.filter((Partner.email == login_id) | (Partner.dsa_code == login_id)).first()
        if user and check_password_hash(user.password, password):
            session.permanent = True
            session['partner_id'] = user.id
            return jsonify({'success': True, 'message': 'Login successful!', 'redirect': '/partner-dashboard.html'})
    else:
        lead = None
        if login_id.upper().startswith('APP-'):
            try: lead = Lead.query.get(int(login_id.split('-')[1])) 
            except: pass
        else: lead = Lead.query.filter_by(email=login_id).first()

        if lead:
            if lead.password:
                if check_password_hash(lead.password, password):
                    session.permanent = True
                    session['customer_lead_id'] = lead.id
                    return jsonify({'success': True, 'message': 'Login Successful!', 'redirect': '/customer-dashboard.html'})
            else:
                session.permanent = True
                session['customer_lead_id'] = lead.id
                return jsonify({'success': True, 'message': 'Tracking Access Granted!', 'redirect': '/customer-dashboard.html'})

    return jsonify({'success': False, 'message': 'Invalid ID or Password!'})

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    reg_type = data.get('type')
    hashed_pw = generate_password_hash(data.get('password'))

    if reg_type == 'Partner':
        if Partner.query.filter_by(email=data.get('email')).first(): return jsonify({'success': False, 'message': 'Email already registered!'})
        dsa_code = f"SC-{random.randint(1000, 9999)}"
        new_partner = Partner(full_name=data.get('name'), email=data.get('email'), phone=data.get('phone'), password=hashed_pw, dsa_code=dsa_code)
        db.session.add(new_partner)
        db.session.commit()
        return jsonify({'success': True, 'message': f'Success! DSA Code: {dsa_code}'})
    else:
        if Lead.query.filter_by(email=data.get('email')).first(): return jsonify({'success': False, 'message': 'Email already registered!'})
        new_lead = Lead(customer_name=data.get('name'), email=data.get('email'), password=hashed_pw, product="Not Selected", amount=0)
        db.session.add(new_lead)
        db.session.commit()
        return jsonify({'success': True, 'message': f'Account Created! Login with your Email. Tracking ID: APP-{new_lead.id}'})

@app.route('/api/submit_application', methods=['POST'])
def api_submit_application():
    if 'customer_lead_id' not in session: return jsonify({'success': False, 'message': 'Unauthorized. Please login again.'})
    data = request.get_json()
    lead = db.session.get(Lead, session['customer_lead_id'])
    if lead:
        lead.product = data.get('product')
        lead.emp_type = data.get('emp')
        try: 
            lead.amount = int(data.get('amount'))
            lead.monthly_income = int(data.get('income'))
        except: 
            lead.amount = 0
            lead.monthly_income = 0
        lead.status = 'Pending' 
        db.session.commit()
        return jsonify({'success': True, 'message': 'Application Submitted Successfully!'})
    return jsonify({'success': False, 'message': 'Customer record not found!'})

# 🟢 AUTO-APPROVAL AI ENGINE 🟢
@app.route('/api/run_ai_engine', methods=['POST'])
def run_ai_engine():
    if 'customer_lead_id' not in session: return jsonify({'success': False})
    lead = db.session.get(Lead, session['customer_lead_id'])
    
    if not lead: return jsonify({'success': False})

    # 1. Mock CIBIL Generation (Based on income for realism)
    if lead.monthly_income > 80000: lead.cibil_score = random.randint(750, 850)
    elif lead.monthly_income > 40000: lead.cibil_score = random.randint(650, 780)
    else: lead.cibil_score = random.randint(550, 700)

    # 2. Risk Calculation (FOIR - Fixed Obligation to Income Ratio)
    # Approx EMI for 15 years at 8.5% is roughly 0.00984 times loan amount per month
    estimated_emi = lead.amount * 0.00984
    foir = estimated_emi / lead.monthly_income if lead.monthly_income > 0 else 1.0

    # 3. Decision Logic
    if lead.cibil_score < 650:
        lead.status = 'Rejected'
        lead.ai_remarks = f"Rejected: Low Credit Score ({lead.cibil_score})"
    elif foir > 0.65:
        lead.status = 'Rejected'
        lead.ai_remarks = f"Rejected: High Debt-to-Income Ratio ({(foir*100):.1f}%)"
    else:
        lead.status = 'Sanctioned'
        lead.ai_remarks = f"Auto-Approved: Excellent Profile (Score: {lead.cibil_score})"

    db.session.commit()
    
    return jsonify({
        'success': True, 
        'cibil': lead.cibil_score,
        'foir': round(foir * 100, 1),
        'status': lead.status,
        'remarks': lead.ai_remarks
    })

@app.route('/api/upload_kyc', methods=['POST'])
def api_upload_kyc():
    if 'customer_lead_id' not in session: return jsonify({'success': False, 'message': 'Please login to your dashboard first.'})
    if 'kyc_file' not in request.files: return jsonify({'success': False, 'message': 'No file selected!'})
        
    file = request.files['kyc_file']
    doc_type = request.form.get('doc_type', 'unknown')
    
    if file.filename != '':
        lead_id = session['customer_lead_id']
        ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'png'
        filename = secure_filename(f"lead_{lead_id}_{doc_type}.{ext}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        lead = db.session.get(Lead, lead_id)
        if lead:
            if doc_type == 'aadhaar': lead.aadhaar_uploaded = True
            elif doc_type == 'pan': lead.pan_uploaded = True
            elif doc_type == 'bank': lead.bank_uploaded = True
            db.session.commit()
            
        return jsonify({'success': True, 'message': 'Document verified and saved!'})
    return jsonify({'success': False})

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/admin_action', methods=['POST'])
def api_admin_action():
    if 'partner_id' not in session: return jsonify({'success': False, 'message': 'Unauthorized'})
    data = request.get_json()
    lead = db.session.get(Lead, data.get('lead_id'))
    if lead:
        lead.status = data.get('action') 
        db.session.commit()
        return jsonify({'success': True, 'message': f'Application {lead.status}!'})
    return jsonify({'success': False, 'message': 'Lead not found!'})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ==========================================
# 📄 HTML PAGE ROUTES
# ==========================================
@app.route('/')
@app.route('/index.html')
def home(): return render_template('index.html')
@app.route('/properties.html')
def properties(): return render_template('properties.html')
@app.route('/loans-details.html')
def loans(): return render_template('loans-details.html')
@app.route('/credit-score.html')
def credit_score(): return render_template('credit-score.html')
@app.route('/upload-kyc.html')
def kyc_vault(): return render_template('upload-kyc.html')

@app.route('/login.html')
def login(): 
    if 'partner_id' in session: return redirect('/partner-dashboard.html')
    if 'customer_lead_id' in session: return redirect('/customer-dashboard.html')
    return render_template('login.html')

@app.route('/partner-dashboard.html')
def partner_dashboard():
    if 'partner_id' not in session: return redirect(url_for('login'))
    current_user = db.session.get(Partner, session['partner_id'])
    if not current_user:
        session.clear()
        return redirect(url_for('login'))
    leads = Lead.query.filter_by(partner_id=current_user.id).order_by(Lead.id.desc()).all()
    total_disbursed = sum([l.amount for l in leads if l.status == 'Disbursed'])
    return render_template('partner-dashboard.html', user=current_user, leads=leads, total_leads=len(leads), sanctioned_loans=len([l for l in leads if l.status in ['Sanctioned', 'Disbursed']]), formatted_disbursed=format_currency(total_disbursed), formatted_commission=format_currency(total_disbursed * 0.015))

@app.route('/customer-dashboard.html')
def customer_dashboard():
    if 'customer_lead_id' not in session: return redirect(url_for('login'))
    lead = db.session.get(Lead, session['customer_lead_id'])
    if not lead:
        session.clear()
        return redirect(url_for('login'))
    return render_template('customer-dashboard.html', lead=lead, amount=format_currency(lead.amount))

if __name__ == '__main__':
    app.run(debug=True, port=5001)