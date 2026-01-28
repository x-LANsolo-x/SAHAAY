"""Pack builder for TherapyHome content packs.

Generates ZIP bundles containing module metadata and references to media files.
"""
import io
import json
import zipfile
from typing import BinaryIO

from services.api import models


def build_therapy_pack(module: models.TherapyModule) -> bytes:
    """Generate a ZIP bundle for a therapy module.
    
    Args:
        module: TherapyModule instance with steps loaded
        
    Returns:
        ZIP file content as bytes
        
    Structure:
        module.json - module metadata
        steps.json - array of step data
        README.txt - human-readable info
    """
    # Build module metadata
    module_data = {
        "id": module.id,
        "title": module.title,
        "description": module.description,
        "module_type": module.module_type,
        "age_range_min": module.age_range_min,
        "age_range_max": module.age_range_max,
        "created_at": module.created_at.isoformat(),
        "step_count": len(module.steps),
    }
    
    # Build steps data
    steps_data = []
    for step in sorted(module.steps, key=lambda s: s.step_number):
        step_dict = {
            "id": step.id,
            "step_number": step.step_number,
            "title": step.title,
            "description": step.description,
            "duration_minutes": step.duration_minutes,
        }
        
        # Parse media references if present
        if step.media_references:
            try:
                step_dict["media_references"] = json.loads(step.media_references)
            except json.JSONDecodeError:
                step_dict["media_references"] = []
        else:
            step_dict["media_references"] = []
            
        steps_data.append(step_dict)
    
    # Build README
    readme_text = f"""Therapy Module: {module.title}
================================

Description: {module.description}
Type: {module.module_type}
Age Range: {module.age_range_min or 'N/A'} - {module.age_range_max or 'N/A'} months
Steps: {len(module.steps)}

This is an offline therapy module pack for the SAHAAY platform.
For more information, visit: https://github.com/sahaay/platform

Files:
- module.json: Module metadata
- steps.json: Step-by-step therapy instructions
- README.txt: This file

Media files referenced in steps.json should be downloaded separately
using the media_references URLs.
"""
    
    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Add module metadata
        zipf.writestr('module.json', json.dumps(module_data, indent=2))
        
        # Add steps
        zipf.writestr('steps.json', json.dumps(steps_data, indent=2))
        
        # Add README
        zipf.writestr('README.txt', readme_text)
    
    zip_buffer.seek(0)
    return zip_buffer.read()


def validate_pack_structure(zip_bytes: bytes) -> tuple[bool, str]:
    """Validate that a ZIP file has the expected therapy pack structure.
    
    Args:
        zip_bytes: ZIP file content
        
    Returns:
        (is_valid, error_message) tuple
    """
    try:
        zip_buffer = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(zip_buffer, 'r') as zipf:
            # Check required files
            required_files = ['module.json', 'steps.json']
            namelist = zipf.namelist()
            
            for req_file in required_files:
                if req_file not in namelist:
                    return False, f"Missing required file: {req_file}"
            
            # Validate JSON structure
            try:
                module_data = json.loads(zipf.read('module.json'))
                if 'title' not in module_data or 'module_type' not in module_data:
                    return False, "Invalid module.json structure"
            except json.JSONDecodeError:
                return False, "module.json is not valid JSON"
            
            try:
                steps_data = json.loads(zipf.read('steps.json'))
                if not isinstance(steps_data, list):
                    return False, "steps.json must be an array"
            except json.JSONDecodeError:
                return False, "steps.json is not valid JSON"
        
        return True, ""
    except zipfile.BadZipFile:
        return False, "Invalid ZIP file"
    except Exception as e:
        return False, f"Validation error: {str(e)}"
