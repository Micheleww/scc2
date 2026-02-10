#!/usr/bin/env python3
"""
Deep integration layer for unified data access into MCP Bus server
"""
import os
import sys
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Add the project root to Python path
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import unified data access module
from unified_data_access import UnifiedDataAccess, DataAccessError

# Create API router
router = APIRouter(prefix="/api/data", tags=["data"])

# Initialize unified data access instance
data_access = UnifiedDataAccess()

# Models for request and response
class DocumentFilter(BaseModel):
    """Document filter model"""
    category: str = None
    document_type: str = None
    limit: int = None
    offset: int = 0

class ScriptFilter(BaseModel):
    """Script filter model"""
    category: str = None
    script_type: str = None
    limit: int = None
    offset: int = 0

@router.get("/health")
async def data_access_health():
    """Check data access service health"""
    return {
        "status": "healthy",
        "service": "unified-data-access",
        "use_db": data_access.use_db,
        "prefer_db": data_access.prefer_db
    }

@router.get("/documents")
async def get_documents(category: str = None, document_type: str = None, limit: int = None, offset: int = 0):
    """Get list of documents"""
    try:
        documents = data_access.get_documents(category=category, document_type=document_type, limit=limit, offset=offset)
        return {
            "success": True,
            "total": len(documents),
            "documents": documents
        }
    except DataAccessError as e:
        raise HTTPException(status_code=500, detail=f"Data access error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/scripts")
async def get_scripts(category: str = None, script_type: str = None, limit: int = None, offset: int = 0):
    """Get list of scripts"""
    try:
        scripts = data_access.get_scripts(category=category, script_type=script_type, limit=limit, offset=offset)
        return {
            "success": True,
            "total": len(scripts),
            "scripts": scripts
        }
    except DataAccessError as e:
        raise HTTPException(status_code=500, detail=f"Data access error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/file/{file_path:path}")
async def get_file_content(file_path: str):
    """Get file content"""
    try:
        content = data_access.fs_access.get_file_content(file_path)
        file_hash = data_access.fs_access.calculate_file_hash(file_path)
        return {
            "success": True,
            "file_path": file_path,
            "content": content,
            "hash": file_hash
        }
    except DataAccessError as e:
        raise HTTPException(status_code=404, detail=f"File not found: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/files/{directory:path}")
async def list_files(directory: str, pattern: str = "*", recursive: bool = True):
    """List files in directory"""
    try:
        files = data_access.fs_access.list_files(directory, pattern=pattern, recursive=recursive)
        return {
            "success": True,
            "directory": directory,
            "pattern": pattern,
            "recursive": recursive,
            "total": len(files),
            "files": files
        }
    except DataAccessError as e:
        raise HTTPException(status_code=500, detail=f"Directory access error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/file/exists/{file_path:path}")
async def file_exists(file_path: str):
    """Check if file exists"""
    try:
        exists = data_access.fs_access.file_exists(file_path)
        return {
            "success": True,
            "file_path": file_path,
            "exists": exists
        }
    except DataAccessError as e:
        raise HTTPException(status_code=500, detail=f"File check error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/test")
async def test_data_access():
    """Test data access functionality"""
    try:
        # Test document access
        documents = data_access.get_documents(limit=2)
        
        # Test script access
        scripts = data_access.get_scripts(limit=2)
        
        # Test file system access
        files = data_access.fs_access.list_files("docs", pattern="*.md", recursive=False)
        
        return {
            "success": True,
            "test_results": {
                "documents": len(documents) > 0,
                "scripts": len(scripts) > 0,
                "files": len(files) > 0
            },
            "sample_documents": documents[:2],
            "sample_scripts": scripts[:2],
            "sample_files": files[:2]
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

# Function to include data access routes in FastAPI app
def include_data_access_routes(app):
    """Include data access routes in FastAPI app"""
    app.include_router(router)
    # Avoid non-ASCII output on Windows consoles using GBK.
    print("Data access routes included successfully")
    return app
