"""
Informe técnico - Aplicación web (Flask) - VERSION COMPLETA FUNCIONAL
Formato profesional completo con todas las secciones FUNCIONANDO
"""

import os
import sqlite3
import base64
import re
import secrets
import traceback
import logging
from io import BytesIO
from datetime import datetime
from contextlib import contextmanager
from dataclasses import dataclass
from flask import Flask, request, redirect, url_for, send_from_directory, render_template_string, flash
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as rcanvas
from PIL import Image
import smtplib
from email.message import EmailMessage

# --- Configuración Mejorada ---
@dataclass
class Config:
    SECRET_KEY: str = os.environ.get('SECRET_KEY', secrets.token_hex(16))
    DB_FILE: str = os.environ.get('DB_FILE', 'informes.db')
    UPLOADS_DIR: str = os.environ.get('UPLOADS_DIR', 'uploads')
    PDF_DIR: str = os.environ.get('PDF_DIR', 'pdfs')
    SMTP_HOST: str = os.environ.get('SMTP_HOST', '')
    SMTP_PORT: int = int(os.environ.get('SMTP_PORT', '587'))
    SMTP_USER: str = os.environ.get('SMTP_USER', '')
    SMTP_PASS: str = os.environ.get('SMTP_PASS', '')
    EMAIL_SENDER: str = os.environ.get('EMAIL_SENDER', '')
    MAX_SIGNATURE_SIZE: int = int(os.environ.get('MAX_SIGNATURE_SIZE', '500000'))

config = Config()
os.makedirs(config.UPLOADS_DIR, exist_ok=True)
os.makedirs(config.PDF_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# --- Database Mejorada ---
def init_db():
    """Inicializar la base de datos con tabla mejorada"""
    with db_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS informes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                institucion TEXT NOT NULL,
                encargado TEXT,
                contacto TEXT,
                comuna TEXT,        
                ciudad TEXT, 
                fecha TEXT NOT NULL,
                equipo TEXT,
                marca_modelo TEXT,
                numero_serie TEXT,
                
                -- Tipo de servicio checkboxes
                servicio_instalacion TEXT,
                servicio_mantenimiento TEXT,
                servicio_correctivo TEXT,
                servicio_visita TEXT,
                servicio_comercial TEXT,
                servicio_otro TEXT,
                servicio_otro_especificar TEXT,
                
                -- Tipo de garantía
                garantia_en_garantia TEXT,
                garantia_fuera_garantia TEXT,
                garantia_en_convenio TEXT,
                
                -- Problema e inspección
                problema_cliente TEXT,
                inspeccion_visual TEXT,
                
                -- Descripción mantenimiento (Aplica/No Aplica)
                mantenimiento_prueba_funcionamiento TEXT,
                mantenimiento_apertura_mecanismos TEXT,
                mantenimiento_desinfeccion TEXT,
                mantenimiento_limpieza_lubricacion TEXT,
                mantenimiento_lubricacion_motores TEXT,
                mantenimiento_calibracion_ejes TEXT,
                mantenimiento_calibracion_software TEXT,
                mantenimiento_verificacion_seguridad TEXT,
                mantenimiento_verificacion_filtraciones TEXT,
                mantenimiento_limpieza_cpu TEXT,
                mantenimiento_cambio_filtro TEXT,
                mantenimiento_reteste_pernos TEXT,
                mantenimiento_reseteo_contadores TEXT,
                mantenimiento_otros TEXT,
                mantenimiento_otros_especificar TEXT,
                
                -- Mediciones
                mediciones_parametros TEXT,
                
                -- Piezas de reemplazo
                piezas_descripcion1 TEXT,
                piezas_cantidad1 TEXT,
                piezas_descripcion2 TEXT,
                piezas_cantidad2 TEXT,
                piezas_descripcion3 TEXT,
                piezas_cantidad3 TEXT,
                piezas_descripcion4 TEXT,
                piezas_cantidad4 TEXT,
                
                -- Detalles y resolución
                detalles_servicio TEXT,
                resolucion_operativo TEXT,
                resolucion_no_operativo TEXT,
                resolucion_requiere_visita TEXT,
                
                -- Encuesta de servicio
                encuesta_presentacion TEXT,
                encuesta_reparacion TEXT,
                encuesta_preparacion TEXT,
                encuesta_plazos TEXT,
                encuesta_nota TEXT,
                encuesta_recomendacion TEXT,
                
                -- Firmas
                tecnico_nombre TEXT,
                cliente_firma TEXT,
                tecnico_firma TEXT,
                pdf_path TEXT,
                created_at TEXT
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_informes_fecha ON informes(fecha)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_informes_institucion ON informes(institucion)')

def recreate_database():
    """Recrear completamente la base de datos con la nueva estructura"""
    db_path = config.DB_FILE
    
    # Si la base de datos existe, eliminarla para recrearla
    if os.path.exists(db_path):
        logger.info("Eliminando base de datos antigua para recrear con nueva estructura...")
        os.remove(db_path)
        logger.info("Base de datos antigua eliminada")
    
    # Recrear la base de datos llamando a init_db()
    init_db()
    logger.info("Base de datos recreada con nueva estructura")

def verify_database_structure():
    """Verificar que la estructura de la base de datos sea correcta"""
    with db_connection() as conn:
        # Obtener información de las columnas
        columns = conn.execute("PRAGMA table_info(informes)").fetchall()
        column_names = [col[1] for col in columns]
        
        logger.info("=== ESTRUCTURA DE LA BASE DE DATOS ===")
        logger.info(f"Total de columnas: {len(column_names)}")
        
        # Mostrar todas las columnas
        for i, col in enumerate(columns, 1):
            logger.info(f"{i:2d}. {col[1]} ({col[2]})")
        
        # Verificar columnas críticas
        critical_columns = ['comuna', 'ciudad']
        for col in critical_columns:
            if col in column_names:
                logger.info(f"✅ Columna '{col}' encontrada")
            else:
                logger.error(f"❌ Columna '{col}' NO encontrada")
        
        # Contar columnas para verificar
        logger.info(f"=== VERIFICACIÓN DE COLUMNAS ===")
        logger.info(f"Columnas en tabla: {len(column_names)}")
        
        return column_names

@contextmanager
def db_connection():
    """Context manager para manejo automático de conexiones a BD"""
    conn = sqlite3.connect(config.DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Error en transacción BD: {str(e)}")
        raise
    finally:
        conn.close()

# Inicializar base de datos
recreate_database()
verify_database_structure()

# --- Validaciones ---
def es_email_valido(email):
    """Validar formato de email"""
    if not email:
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email.strip()) is not None

def validar_formulario(form):
    """Validar datos del formulario"""
    errors = []
    
    if not form.get('institucion') or len(form['institucion'].strip()) == 0:
        errors.append("El campo Institución/Cliente es requerido")
    
    if not form.get('fecha'):
        errors.append("La fecha es requerida")
    
    # Validar firmas (tamaño)
    if form.get('sig_tech') and len(form['sig_tech']) > config.MAX_SIGNATURE_SIZE:
        errors.append("La firma del técnico es demasiado grande")
    
    if form.get('sig_client') and len(form['sig_client']) > config.MAX_SIGNATURE_SIZE:
        errors.append("La firma del cliente es demasiado grande")
    
    return errors

# --- Template HTML COMPLETO (se mantiene igual) ---
INDEX_HTML = '''
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Novamedical - Orden de Trabajo</title>
  <style>
    body {
        font-family: Arial, sans-serif;
        max-width: 1200px;
        margin: 20px auto;
        padding: 20px;
        background: #f5f5f5;
    }
    .container {
        background: white;
        padding: 30px;
        border-radius: 10px;
        box-shadow: 0 2px10px rgba(0,0,0,0.1);
    }
    h2 {
        color: #2c3e50;
        border-bottom: 2px solid #3498db;
        padding-bottom: 10px;
        text-align: center;
    }
    .section {
        margin-bottom: 25px;
        padding: 20px;
        border: 1px solid #ddd;
        border-radius: 5px;
        background: #fafafa;
    }
    .section-title {
        font-weight: bold;
        color: #2c3e50;
        margin-bottom: 15px;
        font-size: 1.1em;
        border-bottom: 1px solid #bdc3c7;
        padding-bottom: 5px;
    }
    label {
        display: block;
        margin-top: 12px;
        font-weight: bold;
        color: #34495e;
    }
    input, textarea, select {
        width: 100%;
        padding: 10px;
        border: 1px solid #bdc3c7;
        border-radius: 5px;
        font-size: 14px;
        box-sizing: border-box;
    }
    textarea {
        min-height: 80px;
        resize: vertical;
    }
    .sig {
        border: 2px solid #7f8c8d;
        height: 150px;
        background: white;
        cursor: crosshair;
        border-radius: 5px;
        margin-top: 5px;
    }
    .row {
        display: flex;
        gap: 20px;
        margin-bottom: 15px;
    }
    .col {
        flex: 1;
    }
    .col-2 { flex: 2; }
    .col-3 { flex: 3; }
    
    button {
        padding: 12px 25px;
        margin-top: 15px;
        background: #3498db;
        color: white;
        border: none;
        border-radius: 5px;
        cursor: pointer;
        font-size: 16px;
        font-weight: bold;
        transition: background 0.3s;
    }
    button:hover {
        background: #2980b9;
    }
    .btn-clear {
        background: #e74c3c;
        padding: 8px 15px;
        font-size: 14px;
    }
    .btn-clear:hover {
        background: #c0392b;
    }
    
    /* Estilos para tablas y checkboxes */
    .checkbox-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 15px;
        margin-top: 10px;
    }
    .checkbox-item {
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .checkbox-group {
        display: flex;
        gap: 15px;
        margin-top: 10px;
    }
    .aplica-group {
        display: flex;
        gap: 10px;
        align-items: center;
    }
    .table-grid {
        display: grid;
        grid-template-columns: 2fr 1fr 2fr 1fr;
        gap: 10px;
        margin-top: 10px;
    }
    .table-header {
        font-weight: bold;
        background: #ecf0f1;
        padding: 8px;
        border-radius: 3px;
    }
    
    .error {
        color: #e74c3c;
        font-size: 0.9em;
        margin-top: 5px;
    }
    .success {
        color: #27ae60;
        font-size: 0.9em;
        margin-top: 5px;
    }
    .required:after {
        content: " *";
        color: #e74c3c;
    }
    .informes-list {
        margin-top: 30px;
    }
    .informes-list li {
        padding: 10px;
        border-bottom: 1px solid #ecf0f1;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .informes-list a {
        color: #3498db;
        text-decoration: none;
        font-weight: bold;
    }
    .informes-list a:hover {
        text-decoration: underline;
    }
  </style>
</head>
<body>
  <div class="container">
    <h2>📋 Novamedical - Orden de Trabajo de Servicio Técnico</h2>
    
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        <div class="messages">
          {% for category, message in messages %}
            <div class="{{ 'error' if category == 'error' else 'success' }}">{{ message }}</div>
          {% endfor %}
        </div>
      {% endif %}
    {% endwith %}
    
    <form method="post" action="/create" onsubmit="return prepareSignatures()">
      
      <!-- Sección: Información del Cliente -->
      <div class="section">
        <div class="section-title">🏢 Información del Cliente</div>
        <div class="row">
          <div class="col">
            <label class="required">Institución/Cliente</label>
            <input name="institucion" value="{{ form_data.institucion or '' }}" required placeholder="Nombre de la institución o cliente">
          </div>
          <div class="col">
            <label class="required">Fecha</label>
            <input name="fecha" type="date" value="{{ form_data.fecha or today }}" required>
          </div>
        </div>
        <div class="row">
          <div class="col">
            <label>Encargado/Responsable</label>
            <input name="encargado" value="{{ form_data.encargado or '' }}" placeholder="Nombre del encargado">
          </div>
          <div class="col">
            <label>Contacto</label>
            <input name="contacto" value="{{ form_data.contacto or '' }}" placeholder="Email o teléfono de contacto">
          </div>
        </div>
        <div class="row">
            <div class="col">
                <label>Comuna</label>
                <input name="comuna" value="{{ form_data.comuna or '' }}" placeholder="Comuna">
            </div>
            <div class="col">
                <label>Ciudad</label>
                <input name="ciudad" value="{{ form_data.ciudad or '' }}" placeholder="Ciudad">
            </div>
        </div>
    </div>

      <!-- Sección: Datos del Equipamiento -->
      <div class="section">
        <div class="section-title">🔧 Datos del Equipamiento</div>
        <div class="row">
          <div class="col">
            <label>Equipo</label>
            <input name="equipo" value="{{ form_data.equipo or '' }}" placeholder="Tipo de equipo médico">
          </div>
          <div class="col">
            <label>Marca/Modelo</label>
            <input name="marca_modelo" value="{{ form_data.marca_modelo or '' }}" placeholder="Marca y modelo del equipo">
          </div>
        </div>
        <div class="row">
          <div class="col">
            <label>Número de Serie</label>
            <input name="numero_serie" value="{{ form_data.numero_serie or '' }}" placeholder="Número de serie del equipo">
          </div>
          <div class="col">
            <label>Técnico Responsable</label>
            <input name="tecnico_nombre" value="{{ form_data.tecnico_nombre or '' }}" placeholder="Nombre del técnico">
          </div>
        </div>
      </div>

      <!-- Sección: Motivo/Razón de la visita -->
      <div class="section">
        <div class="section-title">🎯 Motivo/Razón de la Visita</div>
        <div class="checkbox-grid">
          <div class="checkbox-item">
            <input type="checkbox" name="servicio_instalacion" value="si" {{ 'checked' if 'servicio_instalacion' in form_data and form_data.servicio_instalacion == 'si' else '' }}>
            <label>Instalación/Puesta en marcha/Capacit.</label>
          </div>
          <div class="checkbox-item">
            <input type="checkbox" name="servicio_mantenimiento" value="si" {{ 'checked' if 'servicio_mantenimiento' in form_data and form_data.servicio_mantenimiento == 'si' else '' }}>
            <label>Mantenimiento preventivo</label>
          </div>
          <div class="checkbox-item">
            <input type="checkbox" name="servicio_correctivo" value="si" {{ 'checked' if 'servicio_correctivo' in form_data and form_data.servicio_correctivo == 'si' else '' }}>
            <label>Mantenimiento correctivo</label>
          </div>
          <div class="checkbox-item">
            <input type="checkbox" name="servicio_visita" value="si" {{ 'checked' if 'servicio_visita' in form_data and form_data.servicio_visita == 'si' else '' }}>
            <label>Visita técnica/Diagnóstico</label>
          </div>
          <div class="checkbox-item">
            <input type="checkbox" name="servicio_comercial" value="si" {{ 'checked' if 'servicio_comercial' in form_data and form_data.servicio_comercial == 'si' else '' }}>
            <label>Solicitud comercial</label>
          </div>
          <div class="checkbox-item">
            <input type="checkbox" name="servicio_otro" value="si" {{ 'checked' if 'servicio_otro' in form_data and form_data.servicio_otro == 'si' else '' }}>
            <label>Otro/demo</label>
          </div>
        </div>
        <div class="row">
          <div class="col">
            <label>Especificar "Otro":</label>
            <input name="servicio_otro_especificar" value="{{ form_data.servicio_otro_especificar or '' }}" placeholder="Especificar otro motivo">
          </div>
        </div>
      </div>

      <!-- Sección: Tipo de garantía -->
      <div class="section">
        <div class="section-title">📄 Tipo de Garantía</div>
        <div class="checkbox-group">
          <div class="checkbox-item">
            <input type="radio" name="garantia" value="en_garantia" {{ 'checked' if form_data.get('garantia') == 'en_garantia' else '' }}>
            <label>En garantía</label>
          </div>
          <div class="checkbox-item">
            <input type="radio" name="garantia" value="fuera_garantia" {{ 'checked' if form_data.get('garantia') == 'fuera_garantia' else '' }}>
            <label>Fuera de garantía</label>
          </div>
          <div class="checkbox-item">
            <input type="radio" name="garantia" value="en_convenio" {{ 'checked' if form_data.get('garantia') == 'en_convenio' else '' }}>
            <label>En convenio</label>
          </div>
        </div>
      </div>

      <!-- Sección: Problema reportado e inspección -->
      <div class="section">
        <div class="section-title">🔍 Problema Reportado e Inspección</div>
        <div class="row">
          <div class="col">
            <label>Problema reportado por el cliente</label>
            <textarea name="problema_cliente" placeholder="Describa el problema reportado...">{{ form_data.problema_cliente or '' }}</textarea>
          </div>
          <div class="col">
            <label>Inspección Visual Inicial del equipamiento</label>
            <textarea name="inspeccion_visual" placeholder="Describa la inspección visual...">{{ form_data.inspeccion_visual or '' }}</textarea>
          </div>
        </div>
      </div>

      <!-- Sección: Descripción del Mantenimiento -->
      <div class="section">
        <div class="section-title">🛠️ Descripción del Mantenimiento</div>
        
        <div class="row">
          <div class="col-2"><strong>Actividad</strong></div>
          <div class="col"><strong>Aplica/No Aplica</strong></div>
        </div>
        
        <!-- Filas de mantenimiento (se mantienen igual) -->
        <div class="row">
          <div class="col-2">Prueba de funcionamiento inicial general del equipo.</div>
          <div class="col">
            <div class="aplica-group">
              <input type="radio" name="mantenimiento_prueba_funcionamiento" value="aplica" {{ 'checked' if form_data.mantenimiento_prueba_funcionamiento == 'aplica' else '' }}> Aplica
              <input type="radio" name="mantenimiento_prueba_funcionamiento" value="no_aplica" {{ 'checked' if form_data.mantenimiento_prueba_funcionamiento == 'no_aplica' else '' }}> No Aplica
            </div>
          </div>
        </div>
        
        <div class="row">
          <div class="col-2">Apertura de todos los mecanismos y ejes de movimiento.</div>
          <div class="col">
            <div class="aplica-group">
              <input type="radio" name="mantenimiento_apertura_mecanismos" value="aplica" {{ 'checked' if form_data.mantenimiento_apertura_mecanismos == 'aplica' else '' }}> Aplica
              <input type="radio" name="mantenimiento_apertura_mecanismos" value="no_aplica" {{ 'checked' if form_data.mantenimiento_apertura_mecanismos == 'no_aplica' else '' }}> No Aplica
            </div>
          </div>
        </div>
        
        <div class="row">
          <div class="col-2">Desinfección de equipo completo.</div>
          <div class="col">
            <div class="aplica-group">
              <input type="radio" name="mantenimiento_desinfeccion" value="aplica" {{ 'checked' if form_data.mantenimiento_desinfeccion == 'aplica' else '' }}> Aplica
              <input type="radio" name="mantenimiento_desinfeccion" value="no_aplica" {{ 'checked' if form_data.mantenimiento_desinfeccion == 'no_aplica' else '' }}> No Aplica
            </div>
          </div>
        </div>
        
        <div class="row">
          <div class="col-2">Limpieza y lubricación de todo punto móvil del equipo.</div>
          <div class="col">
            <div class="aplica-group">
              <input type="radio" name="mantenimiento_limpieza_lubricacion" value="aplica" {{ 'checked' if form_data.mantenimiento_limpieza_lubricacion == 'aplica' else '' }}> Aplica
              <input type="radio" name="mantenimiento_limpieza_lubricacion" value="no_aplica" {{ 'checked' if form_data.mantenimiento_limpieza_lubricacion == 'no_aplica' else '' }}> No Aplica
            </div>
          </div>
        </div>
        
        <div class="row">
          <div class="col-2">Lubricación de motores y otros. (solo si aplica)</div>
          <div class="col">
            <div class="aplica-group">
              <input type="radio" name="mantenimiento_lubricacion_motores" value="aplica" {{ 'checked' if form_data.mantenimiento_lubricacion_motores == 'aplica' else '' }}> Aplica
              <input type="radio" name="mantenimiento_lubricacion_motores" value="no_aplica" {{ 'checked' if form_data.mantenimiento_lubricacion_motores == 'no_aplica' else '' }}> No Aplica
            </div>
          </div>
        </div>
        
        <div class="row">
          <div class="col-2">Calibración de los ejes axiales y motores. (solo si aplica)</div>
          <div class="col">
            <div class="aplica-group">
              <input type="radio" name="mantenimiento_calibracion_ejes" value="aplica" {{ 'checked' if form_data.mantenimiento_calibracion_ejes == 'aplica' else '' }}> Aplica
              <input type="radio" name="mantenimiento_calibracion_ejes" value="no_aplica" {{ 'checked' if form_data.mantenimiento_calibracion_ejes == 'no_aplica' else '' }}> No Aplica
            </div>
          </div>
        </div>
        
        <div class="row">
          <div class="col-2">Calibración de software. (solo si aplica)</div>
          <div class="col">
            <div class="aplica-group">
              <input type="radio" name="mantenimiento_calibracion_software" value="aplica" {{ 'checked' if form_data.mantenimiento_calibracion_software == 'aplica' else '' }}> Aplica
              <input type="radio" name="mantenimiento_calibracion_software" value="no_aplica" {{ 'checked' if form_data.mantenimiento_calibracion_software == 'no_aplica' else '' }}> No Aplica
            </div>
          </div>
        </div>
        
        <div class="row">
          <div class="col-2">Verificación de sistemas de seguridad. (solo si aplica)</div>
          <div class="col">
            <div class="aplica-group">
              <input type="radio" name="mantenimiento_verificacion_seguridad" value="aplica" {{ 'checked' if form_data.mantenimiento_verificacion_seguridad == 'aplica' else '' }}> Aplica
              <input type="radio" name="mantenimiento_verificacion_seguridad" value="no_aplica" {{ 'checked' if form_data.mantenimiento_verificacion_seguridad == 'no_aplica' else '' }}> No Aplica
            </div>
          </div>
        </div>
        
        <div class="row">
          <div class="col-2">Verificación por filtraciones varias. (solo si aplica)</div>
          <div class="col">
            <div class="aplica-group">
              <input type="radio" name="mantenimiento_verificacion_filtraciones" value="aplica" {{ 'checked' if form_data.mantenimiento_verificacion_filtraciones == 'aplica' else '' }}> Aplica
              <input type="radio" name="mantenimiento_verificacion_filtraciones" value="no_aplica" {{ 'checked' if form_data.mantenimiento_verificacion_filtraciones == 'no_aplica' else '' }}> No Aplica
            </div>
          </div>
        </div>
        
        <div class="row">
          <div class="col-2">Limpieza de unidad CPU. (solo si aplica)</div>
          <div class="col">
            <div class="aplica-group">
              <input type="radio" name="mantenimiento_limpieza_cpu" value="aplica" {{ 'checked' if form_data.mantenimiento_limpieza_cpu == 'aplica' else '' }}> Aplica
              <input type="radio" name="mantenimiento_limpieza_cpu" value="no_aplica" {{ 'checked' if form_data.mantenimiento_limpieza_cpu == 'no_aplica' else '' }}> No Aplica
            </div>
          </div>
        </div>
        
        <div class="row">
          <div class="col-2">Cambio de Kit de Filtro. (solo si aplica)</div>
          <div class="col">
            <div class="aplica-group">
              <input type="radio" name="mantenimiento_cambio_filtro" value="aplica" {{ 'checked' if form_data.mantenimiento_cambio_filtro == 'aplica' else '' }}> Aplica
              <input type="radio" name="mantenimiento_cambio_filtro" value="no_aplica" {{ 'checked' if form_data.mantenimiento_cambio_filtro == 'no_aplica' else '' }}> No Aplica
            </div>
          </div>
        </div>
        
        <div class="row">
          <div class="col-2">Reteste de pernos, pasadores de motor, etc.</div>
          <div class="col">
            <div class="aplica-group">
              <input type="radio" name="mantenimiento_reteste_pernos" value="aplica" {{ 'checked' if form_data.mantenimiento_reteste_pernos == 'aplica' else '' }}> Aplica
              <input type="radio" name="mantenimiento_reteste_pernos" value="no_aplica" {{ 'checked' if form_data.mantenimiento_reteste_pernos == 'no_aplica' else '' }}> No Aplica
            </div>
          </div>
        </div>
        
        <div class="row">
          <div class="col-2">Reseteo de contadores internos. (solo si aplica)</div>
          <div class="col">
            <div class="aplica-group">
              <input type="radio" name="mantenimiento_reseteo_contadores" value="aplica" {{ 'checked' if form_data.mantenimiento_reseteo_contadores == 'aplica' else '' }}> Aplica
              <input type="radio" name="mantenimiento_reseteo_contadores" value="no_aplica" {{ 'checked' if form_data.mantenimiento_reseteo_contadores == 'no_aplica' else '' }}> No Aplica
            </div>
          </div>
        </div>
        
        <!-- Fila 14 - Otros -->
        <div class="row">
          <div class="col-2">
            <strong>Otros (Especificar)</strong>
            <input type="text" name="mantenimiento_otros_especificar" value="{{ form_data.mantenimiento_otros_especificar or '' }}" placeholder="Especificar otros trabajos...">
          </div>
          <div class="col">
            <div class="aplica-group">
              <input type="radio" name="mantenimiento_otros" value="aplica" {{ 'checked' if form_data.mantenimiento_otros == 'aplica' else '' }}> Aplica
              <input type="radio" name="mantenimiento_otros" value="no_aplica" {{ 'checked' if form_data.mantenimiento_otros == 'no_aplica' else '' }}> No Aplica
            </div>
          </div>
        </div>
      </div>

      <!-- Sección: Mediciones -->
      <div class="section">
        <div class="section-title">📊 Mediciones de Tensión / T° / Presión</div>
        <label>Parámetros de medición realizados</label>
        <textarea name="mediciones_parametros" placeholder="Describa las mediciones realizadas...">{{ form_data.mediciones_parametros or '' }}</textarea>
      </div>

      <!-- Sección: Piezas de reemplazo -->
      <div class="section">
        <div class="section-title">🔩 Piezas de Reemplazo</div>
        <div class="table-grid">
          <div class="table-header">Descripción de repuesto</div>
          <div class="table-header">Cantidad</div>
          <div class="table-header">Descripción de repuesto</div>
          <div class="table-header">Cantidad</div>
          
          <input type="text" name="piezas_descripcion1" value="{{ form_data.piezas_descripcion1 or '' }}" placeholder="Descripción repuesto 1">
          <input type="text" name="piezas_cantidad1" value="{{ form_data.piezas_cantidad1 or '' }}" placeholder="Cantidad">
          <input type="text" name="piezas_descripcion2" value="{{ form_data.piezas_descripcion2 or '' }}" placeholder="Descripción repuesto 2">
          <input type="text" name="piezas_cantidad2" value="{{ form_data.piezas_cantidad2 or '' }}" placeholder="Cantidad">
          
          <input type="text" name="piezas_descripcion3" value="{{ form_data.piezas_descripcion3 or '' }}" placeholder="Descripción repuesto 3">
          <input type="text" name="piezas_cantidad3" value="{{ form_data.piezas_cantidad3 or '' }}" placeholder="Cantidad">
          <input type="text" name="piezas_descripcion4" value="{{ form_data.piezas_descripcion4 or '' }}" placeholder="Descripción repuesto 4">
          <input type="text" name="piezas_cantidad4" value="{{ form_data.piezas_cantidad4 or '' }}" placeholder="Cantidad">
        </div>
      </div>

      <!-- Sección: Detalles del servicio -->
      <div class="section">
        <div class="section-title">📝 Detalles del Servicio u Observaciones</div>
        <textarea name="detalles_servicio" placeholder="Describa detalles adicionales del servicio...">{{ form_data.detalles_servicio or '' }}</textarea>
      </div>

      <!-- Sección: Resolución de los trabajos -->
      <div class="section">
        <div class="section-title">✅ Resolución de los Trabajos</div>
        <div class="checkbox-group">
          <div class="checkbox-item">
            <input type="checkbox" name="resolucion_operativo" value="si" {{ 'checked' if 'resolucion_operativo' in form_data and form_data.resolucion_operativo == 'si' else '' }}>
            <label>Equipo operativo</label>
          </div>
          <div class="checkbox-item">
            <input type="checkbox" name="resolucion_no_operativo" value="si" {{ 'checked' if 'resolucion_no_operativo' in form_data and form_data.resolucion_no_operativo == 'si' else '' }}>
            <label>Equipo no operativo</label>
          </div>
          <div class="checkbox-item">
            <input type="checkbox" name="resolucion_requiere_visita" value="si" {{ 'checked' if 'resolucion_requiere_visita' in form_data and form_data.resolucion_requiere_visita == 'si' else '' }}>
            <label>Requiere nueva visita técnica</label>
          </div>
        </div>
      </div>

      <!-- Sección: Encuesta de Servicio -->
      <div class="section">
        <div class="section-title">⭐ Encuesta de Servicio</div>
        <div class="row">
          <div class="col">
            <label>¿Técnico se presentó correctamente en el servicio?</label>
            <select name="encuesta_presentacion">
              <option value="">Seleccionar</option>
              <option value="si" {{ 'selected' if form_data.encuesta_presentacion == 'si' else '' }}>Sí</option>
              <option value="no" {{ 'selected' if form_data.encuesta_presentacion == 'no' else '' }}>No</option>
            </select>
          </div>
          <div class="col">
            <label>¿Se realiza la reparación del equipamiento?</label>
            <select name="encuesta_reparacion">
              <option value="">Seleccionar</option>
              <option value="si" {{ 'selected' if form_data.encuesta_reparacion == 'si' else '' }}>Sí</option>
              <option value="no" {{ 'selected' if form_data.encuesta_reparacion == 'no' else '' }}>No</option>
            </select>
          </div>
        </div>
        <div class="row">
          <div class="col">
            <label>¿Técnico se encontraba preparado para la visita?</label>
            <select name="encuesta_preparacion">
              <option value="">Seleccionar</option>
              <option value="si" {{ 'selected' if form_data.encuesta_preparacion == 'si' else '' }}>Sí</option>
              <option value="no" {{ 'selected' if form_data.encuesta_preparacion == 'no' else '' }}>No</option>
            </select>
          </div>
          <div class="col">
            <label>¿La visita técnica fue realizada en los plazos estipulados?</label>
            <select name="encuesta_plazos">
              <option value="">Seleccionar</option>
              <option value="si" {{ 'selected' if form_data.encuesta_plazos == 'si' else '' }}>Sí</option>
              <option value="no" {{ 'selected' if form_data.encuesta_plazos == 'no' else '' }}>No</option>
            </select>
          </div>
        </div>
        <div class="row">
          <div class="col">
            <label>¿Qué nota le colocaría al servicio realizado? (de 1 a 10)</label>
            <select name="encuesta_nota">
              <option value="">Seleccionar nota</option>
              {% for i in range(1, 11) %}
                <option value="{{ i }}" {{ 'selected' if form_data.encuesta_nota == i|string else '' }}>{{ i }}</option>
              {% endfor %}
            </select>
          </div>
          <div class="col">
            <label>¿Usted recomendaría nuestro servicio técnico?</label>
            <select name="encuesta_recomendacion">
              <option value="">Seleccionar</option>
              <option value="si" {{ 'selected' if form_data.encuesta_recomendacion == 'si' else '' }}>Sí</option>
              <option value="no" {{ 'selected' if form_data.encuesta_recomendacion == 'no' else '' }}>No</option>
            </select>
          </div>
        </div>
      </div>

      <!-- Sección: Firmas -->
      <div class="section">
        <div class="section-title">✍️ Firmas</div>
        <div class="row">
          <div class="col">
            <label>Firma del Técnico</label>
            <div><canvas id="sigTech" class="sig"></canvas></div>
            <div><button type="button" class="btn-clear" onclick="clearSig('sigTech')">🗑️ Borrar Firma</button></div>
            <input type="hidden" name="sig_tech" id="sig_tech_input">
          </div>
          <div class="col">
            <label>Firma del Cliente/Responsable</label>
            <div><canvas id="sigClient" class="sig"></canvas></div>
            <div><button type="button" class="btn-clear" onclick="clearSig('sigClient')">🗑️ Borrar Firma</button></div>
            <input type="hidden" name="sig_client" id="sig_client_input">
          </div>
        </div>
      </div>

      <button type="submit">📄 Generar PDF & Enviar por Correo</button>
    </form>

    <hr>
    <div class="informes-list">
      <h3>📋 Órdenes de Trabajo Guardadas</h3>
      <ul>
        {% for r in records %}
          <li>
            <span>{{ r.institucion }} — {{ r.fecha }} — OT-{{ r.id }}</span>
            <a href="/download/{{r.id}}">📥 Descargar PDF</a>
          </li>
        {% else %}
          <li>No hay órdenes de trabajo guardadas</li>
        {% endfor %}
      </ul>
    </div>
  </div>

<script>
// JavaScript se mantiene igual
function initCanvas(id){
  const canvas = document.getElementById(id);
  const rect = canvas.getBoundingClientRect();
  
  canvas.width = rect.width;
  canvas.height = rect.height;
  
  const ctx = canvas.getContext('2d');
  
  ctx.lineWidth = 3;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.strokeStyle = '#000000';
  ctx.fillStyle = '#FFFFFF';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  
  let isDrawing = false;
  let lastX = 0;
  let lastY = 0;

  function startDrawing(e) {
    isDrawing = true;
    const pos = getMousePos(canvas, e);
    [lastX, lastY] = [pos.x, pos.y];
    ctx.beginPath();
    ctx.moveTo(lastX, lastY);
  }

  function draw(e) {
    if (!isDrawing) return;
    const pos = getMousePos(canvas, e);
    ctx.lineTo(pos.x, pos.y);
    ctx.stroke();
    [lastX, lastY] = [pos.x, pos.y];
  }

  function stopDrawing() {
    isDrawing = false;
    ctx.closePath();
  }

  function getMousePos(canvas, evt) {
    const rect = canvas.getBoundingClientRect();
    let clientX, clientY;
    
    if (evt.type.includes('touch')) {
      clientX = evt.touches[0].clientX;
      clientY = evt.touches[0].clientY;
    } else {
      clientX = evt.clientX;
      clientY = evt.clientY;
    }
    
    return {
      x: clientX - rect.left,
      y: clientY - rect.top
    };
  }

  canvas.addEventListener('mousedown', startDrawing);
  canvas.addEventListener('mousemove', draw);
  canvas.addEventListener('mouseup', stopDrawing);
  canvas.addEventListener('mouseout', stopDrawing);

  canvas.addEventListener('touchstart', (e) => {
    e.preventDefault();
    startDrawing(e);
  });
  canvas.addEventListener('touchmove', (e) => {
    e.preventDefault();
    draw(e);
  });
  canvas.addEventListener('touchend', (e) => {
    e.preventDefault();
    stopDrawing();
  });
}

function clearSig(id){ 
  const cvs = document.getElementById(id); 
  const ctx = cvs.getContext('2d'); 
  ctx.clearRect(0, 0, cvs.width, cvs.height);
  ctx.fillStyle = '#FFFFFF';
  ctx.fillRect(0, 0, cvs.width, cvs.height);
}

function prepareSignatures(){
  const tech = document.getElementById('sigTech');
  const client = document.getElementById('sigClient');
  
  if(isCanvasBlank(tech) && isCanvasBlank(client)) {
    if(!confirm('No se han capturado firmas. ¿Desea continuar sin firmas?')) {
      return false;
    }
  }
  
  const tdata = tech.toDataURL('image/png');
  const cdata = client.toDataURL('image/png');
  document.getElementById('sig_tech_input').value = tdata;
  document.getElementById('sig_client_input').value = cdata;
  
  return true;
}

function isCanvasBlank(canvas) {
  const context = canvas.getContext('2d');
  const pixelBuffer = new Uint32Array(
    context.getImageData(0, 0, canvas.width, canvas.height).data.buffer
  );
  return !pixelBuffer.some(color => color !== 0);
}

window.onload = function(){ 
  initCanvas('sigTech'); 
  initCanvas('sigClient'); 
}
</script>
</body>
</html>
'''

# --- Routes Mejoradas ---
@app.route('/')
def index():
    """Página principal con lista de informes"""
    try:
        with db_connection() as conn:
            records = conn.execute(
                'SELECT id, institucion, fecha, pdf_path FROM informes ORDER BY id DESC'
            ).fetchall()
        
        today = datetime.now().strftime('%Y-%m-%d')
        form_data = request.args.get('form_data', {})
        
        return render_template_string(
            INDEX_HTML, 
            records=records, 
            today=today,
            form_data=form_data
        )
    
    except Exception as e:
        logger.error(f"Error cargando página principal: {str(e)}")
        flash('Error cargando la página', 'error')
        return render_template_string(INDEX_HTML, records=[], today=datetime.now().strftime('%Y-%m-%d'))

@app.route('/create', methods=['POST'])
def create():
    """Crear nueva orden de trabajo"""
    try:
        form = request.form
        
        # Validar formulario
        errors = validar_formulario(form)
        if errors:
            for error in errors:
                flash(error, 'error')
            return redirect(url_for('index'))
        
        # Extraer TODOS los datos del formulario
        institucion = form.get('institucion', '').strip()
        encargado = form.get('encargado', '').strip()
        contacto = form.get('contacto', '').strip()
        comuna = form.get('comuna', '').strip()
        ciudad = form.get('ciudad', '').strip()
        fecha = form.get('fecha', '')
        equipo = form.get('equipo', '').strip()
        marca_modelo = form.get('marca_modelo', '').strip()
        numero_serie = form.get('numero_serie', '').strip()
        tecnico_nombre = form.get('tecnico_nombre', '').strip()
        
        # Tipo de servicio
        servicio_instalacion = form.get('servicio_instalacion', 'no')
        servicio_mantenimiento = form.get('servicio_mantenimiento', 'no')
        servicio_correctivo = form.get('servicio_correctivo', 'no')
        servicio_visita = form.get('servicio_visita', 'no')
        servicio_comercial = form.get('servicio_comercial', 'no')
        servicio_otro = form.get('servicio_otro', 'no')
        servicio_otro_especificar = form.get('servicio_otro_especificar', '').strip()
        
        # Tipo de garantía
        garantia = form.get('garantia', '')
        garantia_en_garantia = 'si' if garantia == 'en_garantia' else 'no'
        garantia_fuera_garantia = 'si' if garantia == 'fuera_garantia' else 'no'
        garantia_en_convenio = 'si' if garantia == 'en_convenio' else 'no'
        
        # Problema e inspección
        problema_cliente = form.get('problema_cliente', '').strip()
        inspeccion_visual = form.get('inspeccion_visual', '').strip()
        
        # Descripción mantenimiento (Aplica/No Aplica)
        mantenimiento_prueba_funcionamiento = form.get('mantenimiento_prueba_funcionamiento', '')
        mantenimiento_apertura_mecanismos = form.get('mantenimiento_apertura_mecanismos', '')
        mantenimiento_desinfeccion = form.get('mantenimiento_desinfeccion', '')
        mantenimiento_limpieza_lubricacion = form.get('mantenimiento_limpieza_lubricacion', '')
        mantenimiento_lubricacion_motores = form.get('mantenimiento_lubricacion_motores', '')
        mantenimiento_calibracion_ejes = form.get('mantenimiento_calibracion_ejes', '')
        mantenimiento_calibracion_software = form.get('mantenimiento_calibracion_software', '')
        mantenimiento_verificacion_seguridad = form.get('mantenimiento_verificacion_seguridad', '')
        mantenimiento_verificacion_filtraciones = form.get('mantenimiento_verificacion_filtraciones', '')
        mantenimiento_limpieza_cpu = form.get('mantenimiento_limpieza_cpu', '')
        mantenimiento_cambio_filtro = form.get('mantenimiento_cambio_filtro', '')
        mantenimiento_reteste_pernos = form.get('mantenimiento_reteste_pernos', '')
        mantenimiento_reseteo_contadores = form.get('mantenimiento_reseteo_contadores', '')
        mantenimiento_otros = form.get('mantenimiento_otros', '')
        mantenimiento_otros_especificar = form.get('mantenimiento_otros_especificar', '').strip()
        
        # Mediciones
        mediciones_parametros = form.get('mediciones_parametros', '').strip()
        
        # Piezas de reemplazo
        piezas_descripcion1 = form.get('piezas_descripcion1', '').strip()
        piezas_cantidad1 = form.get('piezas_cantidad1', '').strip()
        piezas_descripcion2 = form.get('piezas_descripcion2', '').strip()
        piezas_cantidad2 = form.get('piezas_cantidad2', '').strip()
        piezas_descripcion3 = form.get('piezas_descripcion3', '').strip()
        piezas_cantidad3 = form.get('piezas_cantidad3', '').strip()
        piezas_descripcion4 = form.get('piezas_descripcion4', '').strip()
        piezas_cantidad4 = form.get('piezas_cantidad4', '').strip()
        
        # Detalles del servicio
        detalles_servicio = form.get('detalles_servicio', '').strip()
        
        # Resolución
        resolucion_operativo = form.get('resolucion_operativo', 'no')
        resolucion_no_operativo = form.get('resolucion_no_operativo', 'no')
        resolucion_requiere_visita = form.get('resolucion_requiere_visita', 'no')
        
        # Encuesta de servicio
        encuesta_presentacion = form.get('encuesta_presentacion', '')
        encuesta_reparacion = form.get('encuesta_reparacion', '')
        encuesta_preparacion = form.get('encuesta_preparacion', '')
        encuesta_plazos = form.get('encuesta_plazos', '')
        encuesta_nota = form.get('encuesta_nota', '')
        encuesta_recomendacion = form.get('encuesta_recomendacion', '')
        
        sig_tech = form.get('sig_tech', '')
        sig_client = form.get('sig_client', '')
        
        # Guardar firmas como imágenes
        def save_sig(dataurl, filename_prefix):
            if not dataurl:
                return None
            
            if not dataurl.startswith('data:image/png;base64,'):
                raise ValueError("Formato de imagen no válido")
            
            try:
                header, b64 = dataurl.split(',', 1)
                data = base64.b64decode(b64)
            except Exception as e:
                logger.error(f"Error decodificando firma: {str(e)}")
                return None
            
            if len(data) > config.MAX_SIGNATURE_SIZE:
                raise ValueError("Imagen de firma demasiado grande")
            
            filename = f"{filename_prefix}_{int(datetime.now().timestamp())}_{secrets.token_hex(8)}.png"
            path = os.path.join(config.UPLOADS_DIR, filename)
            
            with open(path, 'wb') as f:
                f.write(data)
            
            return path
        
        tech_sig_path = save_sig(sig_tech, 'tech')
        client_sig_path = save_sig(sig_client, 'client')
        
        # Crear registro en BD con TODOS los campos
        created_at = datetime.now().isoformat()
        
        with db_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO informes 
                (institucion, encargado, contacto, comuna, ciudad, fecha, equipo, marca_modelo, numero_serie,
                 servicio_instalacion, servicio_mantenimiento, servicio_correctivo, servicio_visita,
                 servicio_comercial, servicio_otro, servicio_otro_especificar,
                 garantia_en_garantia, garantia_fuera_garantia, garantia_en_convenio,
                 problema_cliente, inspeccion_visual,
                 mantenimiento_prueba_funcionamiento, mantenimiento_apertura_mecanismos,
                 mantenimiento_desinfeccion, mantenimiento_limpieza_lubricacion,
                 mantenimiento_lubricacion_motores, mantenimiento_calibracion_ejes,
                 mantenimiento_calibracion_software, mantenimiento_verificacion_seguridad,
                 mantenimiento_verificacion_filtraciones, mantenimiento_limpieza_cpu,
                 mantenimiento_cambio_filtro, mantenimiento_reteste_pernos,
                 mantenimiento_reseteo_contadores, mantenimiento_otros, mantenimiento_otros_especificar,
                 mediciones_parametros,
                 piezas_descripcion1, piezas_cantidad1, piezas_descripcion2, piezas_cantidad2,
                 piezas_descripcion3, piezas_cantidad3, piezas_descripcion4, piezas_cantidad4,
                 detalles_servicio,
                 resolucion_operativo, resolucion_no_operativo, resolucion_requiere_visita,
                 encuesta_presentacion, encuesta_reparacion, encuesta_preparacion,
                 encuesta_plazos, encuesta_nota, encuesta_recomendacion,
                 tecnico_nombre, tecnico_firma, cliente_firma, pdf_path, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''', (
                institucion, encargado, contacto, comuna, ciudad, fecha, equipo, marca_modelo, numero_serie,
                servicio_instalacion, servicio_mantenimiento, servicio_correctivo, servicio_visita,
                servicio_comercial, servicio_otro, servicio_otro_especificar,
                garantia_en_garantia, garantia_fuera_garantia, garantia_en_convenio,
                problema_cliente, inspeccion_visual,
                mantenimiento_prueba_funcionamiento, mantenimiento_apertura_mecanismos,
                mantenimiento_desinfeccion, mantenimiento_limpieza_lubricacion,
                mantenimiento_lubricacion_motores, mantenimiento_calibracion_ejes,
                mantenimiento_calibracion_software, mantenimiento_verificacion_seguridad,
                mantenimiento_verificacion_filtraciones, mantenimiento_limpieza_cpu,
                mantenimiento_cambio_filtro, mantenimiento_reteste_pernos,
                mantenimiento_reseteo_contadores, mantenimiento_otros, mantenimiento_otros_especificar,
                mediciones_parametros,
                piezas_descripcion1, piezas_cantidad1, piezas_descripcion2, piezas_cantidad2,
                piezas_descripcion3, piezas_cantidad3, piezas_descripcion4, piezas_cantidad4,
                detalles_servicio,
                resolucion_operativo, resolucion_no_operativo, resolucion_requiere_visita,
                encuesta_presentacion, encuesta_reparacion, encuesta_preparacion,
                encuesta_plazos, encuesta_nota, encuesta_recomendacion,
                tecnico_nombre, tech_sig_path, client_sig_path, '', created_at
            ))
            
            orden_id = cursor.lastrowid
        
        # Generar PDF con TODOS los datos
        pdf_filename = f'orden_trabajo_{orden_id}.pdf'
        pdf_path = os.path.join(config.PDF_DIR, pdf_filename)
        
        generate_pdf(pdf_path, {
            'id': orden_id,
            'institucion': institucion,
            'encargado': encargado,
            'contacto': contacto,
            'comuna': comuna,        
            'ciudad': ciudad,        
            'fecha': fecha,
            'equipo': equipo,
            'marca_modelo': marca_modelo,
            'numero_serie': numero_serie,
            'tecnico_nombre': tecnico_nombre,
            
            # Tipo de servicio
            'servicio_instalacion': servicio_instalacion,
            'servicio_mantenimiento': servicio_mantenimiento,
            'servicio_correctivo': servicio_correctivo,
            'servicio_visita': servicio_visita,
            'servicio_comercial': servicio_comercial,
            'servicio_otro': servicio_otro,
            'servicio_otro_especificar': servicio_otro_especificar,
            
            # Tipo de garantía
            'garantia_en_garantia': garantia_en_garantia,
            'garantia_fuera_garantia': garantia_fuera_garantia,
            'garantia_en_convenio': garantia_en_convenio,
            
            # Problema e inspección
            'problema_cliente': problema_cliente,
            'inspeccion_visual': inspeccion_visual,
            
            # Mantenimiento
            'mantenimiento_prueba_funcionamiento': mantenimiento_prueba_funcionamiento,
            'mantenimiento_apertura_mecanismos': mantenimiento_apertura_mecanismos,
            'mantenimiento_desinfeccion': mantenimiento_desinfeccion,
            'mantenimiento_limpieza_lubricacion': mantenimiento_limpieza_lubricacion,
            'mantenimiento_lubricacion_motores': mantenimiento_lubricacion_motores,
            'mantenimiento_calibracion_ejes': mantenimiento_calibracion_ejes,
            'mantenimiento_calibracion_software': mantenimiento_calibracion_software,
            'mantenimiento_verificacion_seguridad': mantenimiento_verificacion_seguridad,
            'mantenimiento_verificacion_filtraciones': mantenimiento_verificacion_filtraciones,
            'mantenimiento_limpieza_cpu': mantenimiento_limpieza_cpu,
            'mantenimiento_cambio_filtro': mantenimiento_cambio_filtro,
            'mantenimiento_reteste_pernos': mantenimiento_reteste_pernos,
            'mantenimiento_reseteo_contadores': mantenimiento_reseteo_contadores,
            'mantenimiento_otros': mantenimiento_otros,
            'mantenimiento_otros_especificar': mantenimiento_otros_especificar,
            
            # Mediciones
            'mediciones_parametros': mediciones_parametros,
            
            # Piezas
            'piezas_descripcion1': piezas_descripcion1,
            'piezas_cantidad1': piezas_cantidad1,
            'piezas_descripcion2': piezas_descripcion2,
            'piezas_cantidad2': piezas_cantidad2,
            'piezas_descripcion3': piezas_descripcion3,
            'piezas_cantidad3': piezas_cantidad3,
            'piezas_descripcion4': piezas_descripcion4,
            'piezas_cantidad4': piezas_cantidad4,
            
            # Detalles
            'detalles_servicio': detalles_servicio,
            
            # Resolución
            'resolucion_operativo': resolucion_operativo,
            'resolucion_no_operativo': resolucion_no_operativo,
            'resolucion_requiere_visita': resolucion_requiere_visita,
            
            # Encuesta
            'encuesta_presentacion': encuesta_presentacion,
            'encuesta_reparacion': encuesta_reparacion,
            'encuesta_preparacion': encuesta_preparacion,
            'encuesta_plazos': encuesta_plazos,
            'encuesta_nota': encuesta_nota,
            'encuesta_recomendacion': encuesta_recomendacion,
            
            'tech_sig': tech_sig_path,
            'client_sig': client_sig_path
        })
        
        # Actualizar ruta del PDF en BD
        with db_connection() as conn:
            conn.execute(
                'UPDATE informes SET pdf_path = ? WHERE id = ?', 
                (pdf_path, orden_id)
            )
        
        # Intentar enviar email
        recipient = None
        if es_email_valido(contacto):
            recipient = contacto
        elif es_email_valido(encargado):
            recipient = encargado
        
        if recipient:
            try:
                send_email_with_attachment(
                    recipient, 
                    f'Orden de Trabajo Novamedical #{orden_id} - {institucion}',
                    f'Se adjunta la orden de trabajo #{orden_id} para {institucion}.\n\nFecha del servicio: {fecha}\nTécnico: {tecnico_nombre}',
                    pdf_path
                )
                flash(f'✅ Orden #{orden_id} generada y enviada a {recipient}', 'success')
                logger.info(f"Orden {orden_id} enviada a {recipient}")
            
            except Exception as e:
                error_msg = f'Orden #{orden_id} generada pero falló el envío: {str(e)}'
                flash(error_msg, 'error')
                logger.error(f"Error enviando email para orden {orden_id}: {str(e)}")
        else:
            flash(f'✅ Orden #{orden_id} generada correctamente. No se detectó email válido para envío.', 'success')
            logger.info(f"Orden {orden_id} generada sin envío de email")
        
        return redirect(url_for('index'))
    
    except Exception as e:
        logger.error(f"Error creando orden de trabajo: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f'Error interno del servidor: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/download/<int:id>')
def download(id):
    """Descargar PDF de la orden de trabajo"""
    try:
        with db_connection() as conn:
            row = conn.execute(
                'SELECT pdf_path FROM informes WHERE id = ?', 
                (id,)
            ).fetchone()
        
        if not row or not row['pdf_path'] or not os.path.exists(row['pdf_path']):
            flash('PDF no encontrado', 'error')
            return redirect(url_for('index'))
        
        filename = os.path.basename(row['pdf_path'])
        return send_from_directory(config.PDF_DIR, filename, as_attachment=True)
    
    except Exception as e:
        logger.error(f"Error descargando PDF {id}: {str(e)}")
        flash('Error descargando el archivo', 'error')
        return redirect(url_for('index'))

# --- PDF Generation COMPLETO Y FUNCIONAL ---
def generate_pdf(path, data):
    """Generar PDF con diseño mejorado - uso eficiente del espacio"""
    try:
        c = rcanvas.Canvas(path, pagesize=A4)
        width, height = A4
        margin = 40
        y = height - margin
        
        # ===== ENCABEZADO PROFESIONAL =====
        try:
            c.drawImage("C:/Users/Novam/Downloads/Informe_novamedical/novamedical.png", margin -10, y - 70, width=100, height=100)
        except:
            pass
        
        c.setFont('Helvetica-Bold', 14)
        c.drawString(margin + 80, y, 'NOVAMEDICAL CHILE LTDA')
        c.setFont('Helvetica', 9)
        c.drawString(margin + 80, y - 15, '77.899.260-4')
        c.drawString(margin + 80, y - 30, 'Tel: +56 2 3288 1618')
        c.drawString(margin + 80, y - 45, 'Email: serviciotecnico@novamedical.cl')
        
        c.setFont('Helvetica-Bold', 12)
        c.drawString(width - 180, y, f'ORDEN DE TRABAJO N°: {data["id"]}')
        c.setFont('Helvetica', 9)
        c.drawString(width - 180, y - 15, f'Fecha: {data.get("fecha", "")}')
        
        y -= 80
        
        # ===== DATOS DEL CLIENTE - MEJOR DISEÑO =====
        c.setFont('Helvetica-Bold', 11)
        c.drawString(margin, y, 'DATOS DE CLIENTE Y/O USUARIO')
        y -= 15
        
        c.setFont('Helvetica', 9)
        # Primera fila horizontal
        c.drawString(margin, y, "Institución:")
        if data.get('institucion'):
            c.drawString(margin + 50, y, data['institucion'][:40])
        
        c.drawString(width/2, y, "Encargado: ")
        if data.get('encargado'):
            c.drawString(width/2 + 48, y, data['encargado'][:25])
        y -= 12
        
        # Segunda fila horizontal  
        c.drawString(margin, y, "Contacto:")
        if data.get('contacto'):
            c.drawString(margin + 45, y, data['contacto'][:30])
        
        c.drawString(width/2, y, "Comuna:")
        if data.get('comuna'):
            c.drawString(width/2 + 40, y, data['comuna'][:20])
        y -= 12
        
        # Tercera fila horizontal
        c.drawString(margin, y, "Ciudad:")
        if data.get('ciudad'):
            c.drawString(margin + 35, y, data['ciudad'][:20])
        y -= 20
        
        # ===== DATOS DEL EQUIPAMIENTO - AL LADO =====
        c.setFont('Helvetica-Bold', 11)
        c.drawString(margin, y, 'DATOS DEL EQUIPAMIENTO')
        y -= 15
        
        c.setFont('Helvetica', 9)
        c.drawString(margin, y, "Equipo:")
        if data.get('equipo'):
            c.drawString(margin + 35, y, data['equipo'][:25])
        
        c.drawString(width/2, y, "Marca/Modelo: ")
        if data.get('marca_modelo'):
            c.drawString(width/2 + 60, y, data['marca_modelo'][:25])
        y -= 12
        
        c.drawString(margin, y, "N° Serie:")
        if data.get('numero_serie'):
            c.drawString(margin + 40, y, data['numero_serie'][:20])
        
        c.drawString(width/2, y, "Ingeniero:")
        if data.get('tecnico_nombre'):
            c.drawString(width/2 + 40, y, data['tecnico_nombre'][:25])
        y -= 25
        
        # ===== SECCIÓN HORIZONTAL: MOTIVO + GARANTÍA =====
        section_height = 0
        
        # Columna izquierda - MOTIVO DE VISITA
        left_x = margin
        right_x = width/2 + 20
        
        c.setFont('Helvetica-Bold', 11)
        c.drawString(left_x, y, 'MOTIVO DE VISITA')
        
        c.setFont('Helvetica', 9)
        servicios = []
        if data.get('servicio_instalacion') == 'si':
            servicios.append("✓ Instalación/Puesta en marcha")
        if data.get('servicio_mantenimiento') == 'si':
            servicios.append("✓ Mantenimiento preventivo")
        if data.get('servicio_correctivo') == 'si':
            servicios.append("✓ Mantenimiento correctivo")
        if data.get('servicio_visita') == 'si':
            servicios.append("✓ Visita técnica/Diagnóstico")
        if data.get('servicio_comercial') == 'si':
            servicios.append("✓ Solicitud comercial")
        if data.get('servicio_otro') == 'si':
            otros = data.get('servicio_otro_especificar', 'Otro/demo')
            servicios.append(f"✓ Otro: {otros}")
        
        temp_y = y - 15
        for servicio in servicios:
            if temp_y < 100:  # Si se acaba el espacio, nueva página
                c.showPage()
                y = height - margin
                temp_y = y - 15
                c.setFont('Helvetica-Bold', 11)
                c.drawString(left_x, y, 'MOTIVO DE VISITA (cont.)')
                c.setFont('Helvetica', 9)
                y -= 15
            
            c.drawString(left_x + 5, temp_y, servicio)
            temp_y -= 10
        
        left_section_bottom = temp_y
        
        # Columna derecha - TIPO DE GARANTÍA
        c.setFont('Helvetica-Bold', 11)
        c.drawString(right_x, y, 'TIPO DE GARANTÍA')
        
        c.setFont('Helvetica', 9)
        temp_y = y - 15
        if data.get('garantia_en_garantia') == 'si':
            c.drawString(right_x + 5, temp_y, "✓ En garantía")
            temp_y -= 10
        if data.get('garantia_fuera_garantia') == 'si':
            c.drawString(right_x + 5, temp_y, "✓ Fuera de garantía")
            temp_y -= 10
        if data.get('garantia_en_convenio') == 'si':
            c.drawString(right_x + 5, temp_y, "✓ En convenio")
            temp_y -= 10
        
        right_section_bottom = temp_y
        
        # Actualizar Y con la sección más larga
        y = min(left_section_bottom, right_section_bottom) - 15
        
        # ===== PROBLEMA REPORTADO =====
        if data.get('problema_cliente'):
            c.setFont('Helvetica-Bold', 11)
            c.drawString(margin, y, 'PROBLEMA REPORTADO')
            y -= 15
            
            c.setFont('Helvetica', 9)
            problema_lines = split_text(data['problema_cliente'], 80)
            for line in problema_lines:
                if y < 100:
                    c.showPage()
                    y = height - margin - 15
                c.drawString(margin + 5, y, line)
                y -= 10
            y -= 5
        
        # ===== INSPECCIÓN VISUAL =====
        if data.get('inspeccion_visual'):
            c.setFont('Helvetica-Bold', 11)
            c.drawString(margin, y, 'INSPECCIÓN VISUAL')
            y -= 15
            
            c.setFont('Helvetica', 9)
            inspeccion_lines = split_text(data['inspeccion_visual'], 80)
            for line in inspeccion_lines:
                if y < 100:
                    c.showPage()
                    y = height - margin - 15
                c.drawString(margin + 5, y, line)
                y -= 10
            y -= 10
        
        # ===== DESCRIPCIÓN DEL MANTENIMIENTO - DISEÑO MEJORADO =====
        c.setFont('Helvetica-Bold', 11)
        c.drawString(margin, y, 'DESCRIPCIÓN DEL MANTENIMIENTO')
        y -= 20
        
        c.setFont('Helvetica', 9)
        actividades = [
            ("Prueba funcionamiento", data.get('mantenimiento_prueba_funcionamiento')),
            ("Apertura mecanismos", data.get('mantenimiento_apertura_mecanismos')),
            ("Desinfección equipo", data.get('mantenimiento_desinfeccion')),
            ("Limpieza/lubricación", data.get('mantenimiento_limpieza_lubricacion')),
            ("Lubricación motores", data.get('mantenimiento_lubricacion_motores')),
            ("Calibración ejes", data.get('mantenimiento_calibracion_ejes')),
            ("Calibración software", data.get('mantenimiento_calibracion_software')),
            ("Verificación seguridad", data.get('mantenimiento_verificacion_seguridad')),
            ("Verificación filtraciones", data.get('mantenimiento_verificacion_filtraciones')),
            ("Limpieza CPU", data.get('mantenimiento_limpieza_cpu')),
            ("Cambio filtro", data.get('mantenimiento_cambio_filtro')),
            ("Reteste pernos", data.get('mantenimiento_reteste_pernos')),
            ("Reseteo contadores", data.get('mantenimiento_reseteo_contadores')),
        ]
        
        # Diseño en 2 columnas para mantenimiento
        col_width = (width - 2*margin) / 2
        start_y = y
        current_y = y
        
        for i, (actividad, estado) in enumerate(actividades):
            if estado == 'aplica':
                symbol = "✓"
            elif estado == 'no_aplica':
                symbol = "✗"
            else:
                symbol = "○"
            
            # Alternar entre columnas
            if i % 2 == 0:
                x_pos = margin + 5
            else:
                x_pos = margin + col_width + 10
            
            if current_y < 100:  # Nueva página si es necesario
                c.showPage()
                current_y = height - margin - 20
                c.setFont('Helvetica-Bold', 11)
                c.drawString(margin, current_y, 'DESCRIPCIÓN MANTENIMIENTO (cont.)')
                current_y -= 20
                c.setFont('Helvetica', 9)
            
            c.drawString(x_pos, current_y, f"{symbol} {actividad}")
            
            # Solo bajar Y en filas impares (cuando completamos una fila)
            if i % 2 == 1:
                current_y -= 12
        
        # Ajustar Y para la siguiente sección
        y = current_y - 15
        
        # Otros mantenimientos
        if data.get('mantenimiento_otros') == 'aplica' and data.get('mantenimiento_otros_especificar'):
            c.drawString(margin, y, f"✓ Otros: {data['mantenimiento_otros_especificar']}")
            y -= 15
        
        # ===== MEDICIONES =====
        if data.get('mediciones_parametros'):
            c.setFont('Helvetica-Bold', 11)
            c.drawString(margin, y, 'MEDICIONES REALIZADAS')
            y -= 15
            
            c.setFont('Helvetica', 9)
            mediciones_lines = split_text(data['mediciones_parametros'], 80)
            for line in mediciones_lines:
                if y < 100:
                    c.showPage()
                    y = height - margin - 15
                c.drawString(margin + 5, y, line)
                y -= 10
            y -= 10
        
        # ===== PIEZAS DE REEMPLAZO =====
        piezas = []
        if data.get('piezas_descripcion1') and data.get('piezas_cantidad1'):
            piezas.append((data['piezas_descripcion1'], data['piezas_cantidad1']))
        if data.get('piezas_descripcion2') and data.get('piezas_cantidad2'):
            piezas.append((data['piezas_descripcion2'], data['piezas_cantidad2']))
        if data.get('piezas_descripcion3') and data.get('piezas_cantidad3'):
            piezas.append((data['piezas_descripcion3'], data['piezas_cantidad3']))
        if data.get('piezas_descripcion4') and data.get('piezas_cantidad4'):
            piezas.append((data['piezas_descripcion4'], data['piezas_cantidad4']))
        
        if piezas:
            c.setFont('Helvetica-Bold', 11)
            c.drawString(margin, y, 'PIEZAS DE REEMPLAZO')
            y -= 15
            
            c.setFont('Helvetica', 9)
            for descripcion, cantidad in piezas:
                if y < 100:
                    c.showPage()
                    y = height - margin - 15
                c.drawString(margin + 5, y, f"• {descripcion} - Cant: {cantidad}")
                y -= 10
            y -= 5
        
        # ===== DETALLES DEL SERVICIO =====
        if data.get('detalles_servicio'):
            c.setFont('Helvetica-Bold', 11)
            c.drawString(margin, y, 'DETALLES Y OBSERVACIONES')
            y -= 15
            
            c.setFont('Helvetica', 9)
            detalles_lines = split_text(data['detalles_servicio'], 80)
            for line in detalles_lines:
                if y < 100:
                    c.showPage()
                    y = height - margin - 15
                c.drawString(margin + 5, y, line)
                y -= 10
            y -= 10
        
        # ===== RESOLUCIÓN =====
        c.setFont('Helvetica-Bold', 11)
        c.drawString(margin, y, 'RESOLUCIÓN FINAL')
        y -= 15
        
        c.setFont('Helvetica', 9)
        if data.get('resolucion_operativo') == 'si':
            c.drawString(margin + 5, y, "✓ Equipo operativo")
            y -= 10
        if data.get('resolucion_no_operativo') == 'si':
            c.drawString(margin + 5, y, "✓ Equipo no operativo")
            y -= 10
        if data.get('resolucion_requiere_visita') == 'si':
            c.drawString(margin + 5, y, "✓ Requiere nueva visita")
            y -= 10
        
        y -= 20
        
        # ===== FIRMAS =====
                # ===== FIRMAS - CORREGIDAS =====
        if y < 150:
            c.showPage()
            y = height - margin
        
        # Firmas en horizontal - UNA AL LADO DE LA OTRA
        sig_h = 50
        sig_w = 180
        x_sig_tech = margin
        x_sig_client = width - margin - sig_w
        
        # Posición Y común para ambas firmas
        start_y = y
        
        # Firma Técnico (IZQUIERDA)
        c.setFont('Helvetica-Bold', 9)
        c.drawString(x_sig_tech, start_y, "FIRMA INGENIERO")
        c.setFont('Helvetica', 8)
        c.drawString(x_sig_tech, start_y - 12, f"Nombre: {data.get('tecnico_nombre', '')}")
        
        # Dibujar línea para firma del técnico
        c.line(x_sig_tech, start_y - 25, x_sig_tech + sig_w, start_y - 25)
        
        # Imagen de firma del técnico (si existe)
        if data.get('tech_sig') and os.path.exists(data['tech_sig']):
            try:
                processed_tech_path = process_signature_image(data['tech_sig'])
                c.drawImage(processed_tech_path, x_sig_tech, start_y - 80, width=sig_w, height=sig_h)
            except Exception as e:
                c.drawString(x_sig_tech, start_y - 45, "[Firma del técnico]")
        else:
            c.drawString(x_sig_tech, start_y - 45, "[Firma del técnico]")
        
        # Firma Cliente (DERECHA) - MISMA ALTURA QUE EL TÉCNICO
        c.setFont('Helvetica-Bold', 9)
        c.drawString(x_sig_client, start_y, "FIRMA CLIENTE / RESPONSABLE")
        c.setFont('Helvetica', 8)
        c.drawString(x_sig_client, start_y - 12, f"Nombre: {data.get('encargado', '')}")
        
        # Dibujar línea para firma del cliente
        c.line(x_sig_client, start_y - 25, x_sig_client + sig_w, start_y - 25)
        
        # Imagen de firma del cliente (si existe)
        if data.get('client_sig') and os.path.exists(data['client_sig']):
            try:
                processed_client_path = process_signature_image(data['client_sig'])
                c.drawImage(processed_client_path, x_sig_client, start_y - 80, width=sig_w, height=sig_h)
            except Exception as e:
                c.drawString(x_sig_client, start_y - 45, "[Firma del cliente]")
        else:
            c.drawString(x_sig_client, start_y - 45, "[Firma del cliente]")
        
        # Pie de página
        c.setFont('Helvetica', 7)
        c.drawString(margin, 30, f"Documento generado automáticamente - Novamedical Services - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        c.save()
        logger.info(f"PDF mejorado generado: {path}")
    
    except Exception as e:
        logger.error(f"Error generando PDF {path}: {str(e)}")
        raise

def process_signature_image(image_path):
    """Procesar imagen de firma para evitar fondos negros"""
    try:
        base, ext = os.path.splitext(image_path)
        processed_path = f"{base}_processed{ext}"
        
        with Image.open(image_path) as img:
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            background = Image.new('RGBA', img.size, (255, 255, 255, 255))
            combined = Image.alpha_composite(background, img)
            rgb_img = combined.convert('RGB')
            rgb_img.save(processed_path, 'PNG')
            
        return processed_path
        
    except Exception as e:
        logger.warning(f"Error procesando imagen {image_path}: {str(e)}")
        return image_path

def split_text(text, n):
    """Dividir texto en líneas de máximo n caracteres"""
    if not text:
        return []
    
    words = text.split(' ')
    lines = []
    cur = ''
    
    for w in words:
        if len(cur) + len(w) + 1 <= n:
            cur = (cur + ' ' + w).strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
            while len(cur) > n:
                lines.append(cur[:n])
                cur = cur[n:]
    
    if cur:
        lines.append(cur)
    
    return lines

def send_email_with_attachment(recipient, subject, body, attachment_path):
    """Enviar email con archivo adjunto"""
    if not config.SMTP_HOST or config.SMTP_HOST == 'smtp.example.com':
        raise RuntimeError('Servidor SMTP no configurado.')
    
    if not os.path.exists(attachment_path):
        raise FileNotFoundError(f"Archivo adjunto no encontrado: {attachment_path}")
    
    try:
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = config.EMAIL_SENDER or config.SMTP_USER
        msg['To'] = recipient
        msg.set_content(body)
        
        with open(attachment_path, 'rb') as f:
            file_data = f.read()
            file_name = os.path.basename(attachment_path)
        
        msg.add_attachment(
            file_data,
            maintype='application',
            subtype='pdf',
            filename=file_name
        )
        
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.starttls()
            if config.SMTP_USER and config.SMTP_PASS:
                server.login(config.SMTP_USER, config.SMTP_PASS)
            server.send_message(msg)
        
        logger.info(f"Email enviado correctamente a {recipient}")
    
    except Exception as e:
        logger.error(f"Error enviando email a {recipient}: {str(e)}")
        raise

# --- Health Check ---
@app.route('/health')
def health_check():
    """Endpoint de verificación de salud"""
    try:
        with db_connection() as conn:
            conn.execute('SELECT 1').fetchone()
        
        required_dirs = [config.UPLOADS_DIR, config.PDF_DIR]
        for directory in required_dirs:
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
        
        return {
            'status': 'healthy',
            'database': 'ok',
            'directories': 'ok',
            'timestamp': datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }, 500

# --- Run ---
# --- Configuración para Railway ---
if __name__ == '__main__':
    logger.info("🚀 Iniciando Novamedical Orders en Railway")
    logger.info(f"📁 Directorio de trabajo: {os.getcwd()}")
    logger.info(f"🗄️ Base de datos: {config.DB_FILE}")
    
    # Verificar estructura de base de datos
    try:
        verify_database_structure()
    except Exception as e:
        logger.error(f"Error verificando BD: {e}")
    
    # Configuración específica para Railway
    port = int(os.environ.get('PORT', 5000))
    host = '0.0.0.0'  # CRÍTICO para Railway
    
    logger.info(f"🌐 Servidor iniciando en: {host}:{port}")
    
    # Verificar si el logo existe
    try:
        if os.path.exists("novamedical.png"):
            logger.info("✅ Logo encontrado")
        else:
            logger.warning("⚠️ Logo no encontrado")
    except:
        logger.warning("⚠️ No se pudo verificar el logo")
    
    # Iniciar servidor
    app.run(
        host=host,
        port=port,
        debug=False  # Siempre False en producción
    )
