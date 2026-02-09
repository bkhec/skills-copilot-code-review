"""
Announcements endpoints for the High School Management System API
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Dict, Any, List, Optional
from datetime import datetime
from bson import ObjectId
import logging

from ..database import announcements_collection, teachers_collection

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)

# Constants
MAX_MESSAGE_LENGTH = 500


def verify_teacher(teacher_username: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Verify teacher authentication and return teacher document"""
    if not teacher_username:
        logger.warning("Authentication attempt without username")
        raise HTTPException(
            status_code=401, detail="Authentication required for this action")
    
    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        logger.warning(f"Failed authentication attempt for username: {teacher_username}")
        raise HTTPException(
            status_code=401, detail="Invalid teacher credentials")
    
    return teacher


def validate_message(message: str) -> None:
    """Validate announcement message"""
    if not message or len(message.strip()) == 0:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    if len(message) > MAX_MESSAGE_LENGTH:
        raise HTTPException(
            status_code=400, 
            detail=f"Message too long (max {MAX_MESSAGE_LENGTH} characters)")


def serialize_announcement(announcement: Dict[str, Any]) -> Dict[str, Any]:
    """Convert MongoDB document to JSON-serializable format"""
    if "_id" in announcement:
        announcement["id"] = str(announcement["_id"])
        del announcement["_id"]
    return announcement


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def get_announcements(active_only: bool = Query(True)) -> List[Dict[str, Any]]:
    """
    Get all announcements

    - active_only: If True, only return announcements that are currently active based on dates
    """
    query = {}
    
    if active_only:
        now = datetime.utcnow()
        query = {
            "$or": [
                # No start_date, only check expiration
                {
                    "start_date": {"$exists": False},
                    "expiration_date": {"$gte": now}
                },
                # Has start_date and within range
                {
                    "start_date": {"$lte": now},
                    "expiration_date": {"$gte": now}
                }
            ]
        }

    announcements = []
    for announcement in announcements_collection.find(query).sort("created_at", -1):
        announcements.append(serialize_announcement(announcement))

    return announcements


@router.get("/{announcement_id}", response_model=Dict[str, Any])
def get_announcement(announcement_id: str) -> Dict[str, Any]:
    """Get a specific announcement by ID"""
    try:
        announcement = announcements_collection.find_one({"_id": ObjectId(announcement_id)})
        if not announcement:
            raise HTTPException(status_code=404, detail="Announcement not found")
        
        return serialize_announcement(announcement)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching announcement {announcement_id}: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid announcement ID")


@router.post("", response_model=Dict[str, Any])
@router.post("/", response_model=Dict[str, Any])
def create_announcement(
    message: str,
    expiration_date: str,
    start_date: Optional[str] = None,
    teacher: Dict[str, Any] = Depends(verify_teacher)
) -> Dict[str, Any]:
    """
    Create a new announcement - requires teacher authentication

    - message: The announcement message (max 500 characters)
    - expiration_date: ISO format date string (YYYY-MM-DD) when announcement expires
    - start_date: Optional ISO format date string when announcement becomes active
    """
    # Validate message
    validate_message(message)

    # Validate and parse dates
    try:
        exp_date = datetime.fromisoformat(expiration_date)
        
        # Ensure expiration is in the future
        if exp_date < datetime.utcnow():
            raise HTTPException(
                status_code=400, detail="Expiration date must be in the future")
        
        start = None
        if start_date:
            start = datetime.fromisoformat(start_date)
            if start > exp_date:
                raise HTTPException(
                    status_code=400, detail="Start date must be before expiration date")
    except ValueError as e:
        logger.error(f"Date parsing error: {str(e)}")
        raise HTTPException(
            status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Create announcement document
    announcement = {
        "message": message,
        "expiration_date": exp_date,
        "created_at": datetime.utcnow(),
        "created_by": teacher["_id"]
    }
    
    if start:
        announcement["start_date"] = start

    try:
        result = announcements_collection.insert_one(announcement)
        announcement["_id"] = result.inserted_id
        logger.info(f"Announcement created by {teacher['_id']}: {announcement['_id']}")
        return serialize_announcement(announcement)
    except Exception as e:
        logger.error(f"Error creating announcement: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create announcement")


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    message: Optional[str] = None,
    expiration_date: Optional[str] = None,
    start_date: Optional[str] = None,
    teacher: Dict[str, Any] = Depends(verify_teacher)
) -> Dict[str, Any]:
    """
    Update an announcement - requires teacher authentication

    - announcement_id: ID of the announcement to update
    - message: New message (optional, max 500 characters)
    - expiration_date: New expiration date in ISO format (optional)
    - start_date: New start date in ISO format (optional, use empty string to remove)
    """
    # Validate message if provided
    if message is not None:
        validate_message(message)

    try:
        # Check if announcement exists
        announcement = announcements_collection.find_one({"_id": ObjectId(announcement_id)})
        if not announcement:
            raise HTTPException(status_code=404, detail="Announcement not found")

        update_fields = {}
        
        if message is not None:
            update_fields["message"] = message
        
        if expiration_date is not None:
            try:
                exp_date = datetime.fromisoformat(expiration_date)
                if exp_date < datetime.utcnow():
                    raise HTTPException(
                        status_code=400, detail="Expiration date must be in the future")
                update_fields["expiration_date"] = exp_date
            except ValueError:
                raise HTTPException(
                    status_code=400, detail="Invalid expiration date format. Use YYYY-MM-DD")
        
        if start_date is not None:
            if start_date == "":
                # Remove start_date
                announcements_collection.update_one(
                    {"_id": ObjectId(announcement_id)},
                    {"$unset": {"start_date": ""}}
                )
            else:
                try:
                    start = datetime.fromisoformat(start_date)
                    exp = update_fields.get("expiration_date", announcement.get("expiration_date"))
                    if start > exp:
                        raise HTTPException(
                            status_code=400, detail="Start date must be before expiration date")
                    update_fields["start_date"] = start
                except ValueError:
                    raise HTTPException(
                        status_code=400, detail="Invalid start date format. Use YYYY-MM-DD")

        if update_fields:
            announcements_collection.update_one(
                {"_id": ObjectId(announcement_id)},
                {"$set": update_fields}
            )

        # Return updated announcement
        updated = announcements_collection.find_one({"_id": ObjectId(announcement_id)})
        logger.info(f"Announcement updated by {teacher['_id']}: {announcement_id}")
        return serialize_announcement(updated)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating announcement {announcement_id}: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid announcement ID")


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: str,
    teacher: Dict[str, Any] = Depends(verify_teacher)
) -> Dict[str, str]:
    """
    Delete an announcement - requires teacher authentication

    - announcement_id: ID of the announcement to delete
    """
    try:
        result = announcements_collection.delete_one({"_id": ObjectId(announcement_id)})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Announcement not found")
        
        logger.info(f"Announcement deleted by {teacher['_id']}: {announcement_id}")
        return {"message": "Announcement deleted successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting announcement {announcement_id}: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid announcement ID")
