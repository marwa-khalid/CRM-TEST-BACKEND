from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Body
from typing import Dict, Any, List
from pydantic import BaseModel, HttpUrl
from appflow.services.roboflow_service import roboflow_service
from appflow.services.cloudinary_service import cloudinary_service
import logging
import base64
import io
import cloudinary.uploader

logger = logging.getLogger(__name__)

roboflow_router = APIRouter(prefix="/car-damage-detection", tags=["Car Damage Detection"])


class ImageURLRequest(BaseModel):
    """Request model for URL-based damage detection"""
    image_urls: List[str]
    include_summary: bool = True
    include_annotated_image: bool = False

@roboflow_router.get("/health", response_model=Dict[str, Any])
def roboflow_health() -> Dict[str, Any]:
    """Report the configured Roboflow inference target and whether it's reachable.
    After setting ROBOFLOW_API_URL to a self-hosted server, hit this to confirm
    the backend can reach it (`reachable: true` + `self_hosted: true`)."""
    return roboflow_service.health_check()


@roboflow_router.post("/detect", response_model=Dict[str, Any])
async def detect_car_damage(
    images: list[UploadFile] = File(..., description="Image files to analyze for car damage (1 or more)"),
    include_summary: bool = True,
    include_annotated_image: bool = False
) -> Dict[str, Any]:
    """
    Detect car damage in uploaded vehicle images using Roboflow AI.
    
    This endpoint analyzes uploaded images to identify various types of vehicle damage
    including scratches, dents, broken parts, and other damage indicators.
    Can process single or multiple images and returns a union of all detected damage.
    
    Args:
        images: List of image files to analyze (JPEG, PNG, BMP, TIFF, TIF) - minimum 1 image
        include_summary: Whether to include a summary of detected damage
        include_annotated_image: Whether to include annotated images with bounding boxes
        
    Returns:
        Dict containing:
        - predictions: Combined detection results from all images
        - summary: (Optional) Processed summary of all detected damage findings
        - annotated_images: (Optional) List of data URL encoded images with damage areas highlighted
        - metadata: Information about the analysis including per-image details
        - normalized_report: (Optional) Structured report combining all damage findings
        
    Raises:
        HTTPException: 400 if file validation fails or no images provided
        HTTPException: 500 if detection service fails
    """
    try:
        # Validate that at least one image is provided
        if not images or len(images) == 0:
            raise HTTPException(
                status_code=400,
                detail="At least one image file is required"
            )
        
        logger.info(f"Received car damage detection request for {len(images)} image(s)")
        
        # Process all images and collect results
        all_predictions = []
        all_annotated_images = []
        image_metadata = []
        combined_damage_types = []
        combined_areas = []
        all_confidence_scores = []
        
        for i, image in enumerate(images):
            logger.info(f"Processing image {i+1}/{len(images)}: {image.filename}")
            
            # Upload image to Cloudinary
            try:
                cloudinary_result = cloudinary_service.upload_image(
                    file=image,
                    folder="car-damage-detection"
                )
                uploaded_image_url = cloudinary_result.get("secure_url")
                cloudinary_public_id = cloudinary_result.get("public_id")
                logger.info(f"Image {i+1} uploaded to Cloudinary: {uploaded_image_url}")
            except Exception as e:
                logger.error(f"Failed to upload image {i+1} to Cloudinary: {str(e)}")
                uploaded_image_url = None
                cloudinary_public_id = None
            
            # Perform car damage detection for this image
            detection_result = await roboflow_service.detect_car_damage(image, include_annotated_image,i)
            
            # Store individual image metadata
            image_metadata.append({
                "filename": image.filename,
                "content_type": image.content_type,
                "image_index": i,
                "model_used": roboflow_service.workflow_id,
                "uploaded_image_url": uploaded_image_url,
                "cloudinary_public_id": cloudinary_public_id
            })
            
            # Collect predictions from this image and apply NMS per image
            image_predictions = detection_result.get("predictions", [])
            nms_predictions = roboflow_service.apply_nms_per_image(image_predictions, i,iou_threshold=0.5)
            all_predictions.extend(nms_predictions)
            
            # Collect annotated image if requested
            if include_annotated_image and detection_result.get("annotated_image"):
                annotated_data_url = detection_result.get("annotated_image")
                annotated_cloudinary_url = None
                annotated_cloudinary_public_id = None
                
                # Upload annotated image to Cloudinary
                try:
                    # Extract base64 data from data URL (format: "data:image/jpeg;base64,...")
                    if annotated_data_url.startswith("data:image"):
                        base64_data = annotated_data_url.split(",")[1]
                        image_bytes = base64.b64decode(base64_data)
                        
                        # Upload to Cloudinary
                        annotated_result = cloudinary.uploader.upload(
                            image_bytes,
                            folder="car-damage-detection/annotated",
                            resource_type="auto",
                            format="jpg",
                            quality="auto:good"
                        )
                        
                        annotated_cloudinary_url = annotated_result.get("secure_url")
                        annotated_cloudinary_public_id = annotated_result.get("public_id")
                        logger.info(f"Annotated image {i+1} uploaded to Cloudinary: {annotated_cloudinary_url}")
                except Exception as e:
                    logger.error(f"Failed to upload annotated image {i+1} to Cloudinary: {str(e)}")
                
                all_annotated_images.append({
                    "file_path": annotated_cloudinary_url or annotated_data_url,
                    "data_url": annotated_data_url,
                    "cloudinary_url": annotated_cloudinary_url,
                    "cloudinary_public_id": annotated_cloudinary_public_id,
                    "original_filename": image.filename,
                    "image_index": i
                })
            
            # Extract damage types and areas for union (using NMS-processed predictions)
            for pred in nms_predictions:
                cls = pred.get("class", "")
                if not cls:
                    continue
                
                # class like "bonnet-dent" -> area "bonnet", type "dent"
                parts = cls.split("-")
                if len(parts) == 2:
                    area, d_type = parts
                    combined_areas.append(area.replace("_", " "))
                    combined_damage_types.append(d_type.replace("_", " "))
                else:
                    combined_damage_types.append(cls.replace("_", " "))
                
                # Collect confidence scores
                confidence = pred.get("confidence", 0.0)
                all_confidence_scores.append(confidence)
        
        # Apply cross-image merging and confidence filtering
        merged_predictions = roboflow_service.merge_detections_across_images(all_predictions, iou_threshold=0.3)
        accepted_predictions, review_predictions = roboflow_service.apply_confidence_filtering(merged_predictions)
        
        # Calculate weighted confidence
        confidence_analysis = roboflow_service.calculate_weighted_confidence(accepted_predictions)
        
        # Prepare base response with combined results
        response: Dict[str, Any] = {
            "predictions": accepted_predictions,
            "review_predictions": review_predictions,
            "metadata": {
                "total_images": len(images),
                "model_used": roboflow_service.workflow_id,
                "images": image_metadata,
                "processing_stats": {
                    "total_detections": len(all_predictions),
                    "after_nms": len(all_predictions),
                    "after_merging": len(merged_predictions),
                    "accepted": len(accepted_predictions),
                    "review": len(review_predictions)
                }
            }
        }
        
        # Add summary if requested
        if include_summary:
            # Create combined summary using accepted predictions and weighted confidence
            accepted_confidence_scores = [pred.get("confidence", 0.0) for pred in accepted_predictions]
            combined_summary = {
                "total_detections": len(accepted_predictions),
                "review_detections": len(review_predictions),
                "damage_types": list(set(combined_damage_types)),
                "confidence_scores": accepted_confidence_scores,
                "average_confidence": sum(accepted_confidence_scores) / len(accepted_confidence_scores) if accepted_confidence_scores else 0.0,
                "weighted_confidence": confidence_analysis.get("overall_confidence", 0.0),
                "confidence_band": confidence_analysis.get("confidence_band", "Low"),
                "per_class_confidences": confidence_analysis.get("per_class_confidences", {}),
                "class_weights": confidence_analysis.get("class_weights", {}),
                "high_severity_count":confidence_analysis.get("high_severity_count",0)
            }
            response["summary"] = combined_summary

            # Build normalized payload compatible with VehicleDamageAIReportIn (without IDs)
            uniq_areas = ", ".join(sorted(set(combined_areas))) if combined_areas else None
            uniq_types = ", ".join(sorted(set(combined_damage_types))) if combined_damage_types else None

            # Infer damage side from detected areas
            def infer_damage_side(areas):
                """Infer damage side from detected areas based on Roboflow model class names"""
                if not areas:
                    return ""
                
                # Convert to lowercase for comparison
                areas_lower = [area.lower() for area in areas]
                
                # Based on actual Roboflow model class names from the service
                # Front areas (from model: bonnet-dent, bumper-damage, headlight-damage)
                front_indicators = ['bonnet', 'hood', 'bumper', 'headlight', 'grille', 'radiator', 'front']
                # Rear areas (from model: tail-light-damage)
                rear_indicators = ['boot', 'trunk', 'tailgate', 'taillight', 'rear', 'back', 'tail']
                # Side areas (from model: door-dent, side-mirror-damage)
                side_indicators = ['door', 'mirror', 'side', 'wing', 'fender']
                # Left side indicators
                left_indicators = ['left', 'driver', 'nearside']
                # Right side indicators  
                right_indicators = ['right', 'passenger', 'offside']
                
                # Check for specific side indicators first (most specific)
                for area in areas_lower:
                    if any(indicator in area for indicator in left_indicators):
                        return "Left"
                    if any(indicator in area for indicator in right_indicators):
                        return "Right"
                
                # Check for side areas (door, mirror) - these are typically side damage
                for area in areas_lower:
                    if any(indicator in area for indicator in side_indicators):
                        # If we have side areas but no specific left/right indicator, 
                        # we can't determine which side, so return empty
                        return ""
                
                # Check for front/rear indicators
                for area in areas_lower:
                    if any(indicator in area for indicator in front_indicators):
                        return "Front"
                    if any(indicator in area for indicator in rear_indicators):
                        return "Rear"
                
                # Default to empty if no clear side can be determined
                return ""
            
            inferred_damage_side = infer_damage_side(combined_areas)

            # Use weighted confidence for severity calculation
            weighted_conf = combined_summary.get("weighted_confidence", 0.0)
            confidence_percent = int(round(weighted_conf * 100))
            confidence_band = combined_summary.get("confidence_band", "Low")
            
            # Map confidence band to severity
            if confidence_band == "High":
                severity = "High"
            elif confidence_band == "Medium":
                severity = "Medium"
            else:
                severity = "Low"

            # Generate suggested repair action based on combined damage types
            suggested_repair_action = None
            if combined_damage_types:
                if any("dent" in dt.lower() for dt in combined_damage_types):
                    suggested_repair_action = "Repair dents and paint"
                elif any("scratch" in dt.lower() for dt in combined_damage_types):
                    suggested_repair_action = "Polish and touch-up paint"
                elif any("crack" in dt.lower() or "break" in dt.lower() for dt in combined_damage_types):
                    suggested_repair_action = "Replace damaged parts"
                else:
                    suggested_repair_action = "Professional assessment required"

            response["normalized_report"] = {
                # Format matching /damage/ai payload structure for single vehicle
                "client_area_of_damage": uniq_areas or "",
                "client_unrelated_damage": "",
                "client_vehicle_status_id": None,  # Will be set by frontend
                "damage_diagram": {
                    "ai_analysis": "comprehensive",
                    "confidence": "high" if confidence_percent >= 80 else "medium" if confidence_percent >= 60 else "low",
                    "detected_areas": list(set(combined_areas)) or [],
                    "detected_types": list(set(combined_damage_types)) or []
                },
                "damage_side": inferred_damage_side,
                "area_of_damage": uniq_areas or "",
                "type_of_damage": uniq_types or "",
                "severity": severity or "",
                "confidence_percent": confidence_percent or 0,
                "total_damaged_points_identified": combined_summary.get("total_detections", 0),
                "suggested_repair_action": suggested_repair_action or "",
                "vehicle_status_id": None,  # Will be set by frontend
                "raw_result": {
                    "predictions": accepted_predictions,
                    "review_predictions": review_predictions,
                    "metadata": response["metadata"],
                    "summary": combined_summary,
                    "confidence_analysis": confidence_analysis,
                }
            }

            # Add annotated images if requested
            if include_annotated_image and all_annotated_images:
                response["annotated_images"] = all_annotated_images
        
        logger.info(f"Successfully processed car damage detection for {len(images)} image(s)")
        
        return response
        
    except HTTPException as e:
        logger.error(f"HTTP error in car damage detection: {e.detail}")
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in car damage detection: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred during car damage detection"
        )


@roboflow_router.post("/get-image-report", response_model=Dict[str, Any])
async def detect_car_damage_from_url(request: ImageURLRequest) -> Dict[str, Any]:
    """
    Detect car damage from image URLs using Roboflow AI.
    
    This endpoint analyzes images from URLs (no file upload needed) to identify various types 
    of vehicle damage including scratches, dents, broken parts, and other damage indicators.
    Can process single or multiple image URLs and returns a union of all detected damage.
    Returns the response in the same format as /damage-report/{claim_id}/client or third-party endpoints.
    
    Args:
        request: ImageURLRequest containing:
            - image_urls: List of image URLs to analyze (minimum 1 URL)
            - include_summary: Whether to include a summary of detected damage (default: True)
            - include_annotated_image: Whether to include annotated images with bounding boxes (default: False)
        
    Returns:
        Dict containing:
        - predictions: Combined detection results from all images
        - summary: Processed summary of all detected damage findings
        - normalized_report: Structured report combining all damage findings (matching damage report format)
        - images: List of processed images with URLs
        - annotated_images: (Optional) List of data URL encoded images with damage areas highlighted
        - metadata: Information about the analysis including per-image details
        
    Raises:
        HTTPException: 400 if URL validation fails or no URLs provided
        HTTPException: 500 if detection service fails
        
    Example:
        POST /car-damage-detection/get-image-report
        {
            "image_urls": ["https://example.com/car1.jpg"],
            "include_summary": true,
            "include_annotated_image": false
        }
    """
    try:
        # Validate that at least one URL is provided
        if not request.image_urls or len(request.image_urls) == 0:
            raise HTTPException(
                status_code=400,
                detail="At least one image URL is required"
            )
        
        logger.info(f"Received car damage detection request for {len(request.image_urls)} image URL(s)")
        
        # Process all images and collect results
        all_predictions = []
        all_annotated_images = []
        image_metadata = []
        combined_damage_types = []
        combined_areas = []
        all_confidence_scores = []
        
        for i, image_url in enumerate(request.image_urls):
            logger.info(f"Processing image URL {i+1}/{len(request.image_urls)}: {image_url}")
            
            # Perform car damage detection for this image URL
            detection_result = await roboflow_service.detect_car_damage_from_url(
                image_url, 
                request.include_annotated_image
            )
            
            # Store individual image metadata
            image_metadata.append({
                "image_url": image_url,
                "image_index": i,
                "model_used": roboflow_service.workflow_id
            })
            
            # Collect predictions from this image and apply NMS per image
            image_predictions = detection_result.get("predictions", [])
            nms_predictions = roboflow_service.apply_nms_per_image(image_predictions, i, iou_threshold=0.5)
            all_predictions.extend(nms_predictions)
            
            # Collect annotated image if requested
            if request.include_annotated_image and detection_result.get("annotated_image"):
                all_annotated_images.append({
                    "file_path": detection_result.get("annotated_image"),
                    "data_url": detection_result.get("annotated_image"),
                    "original_url": image_url,
                    "image_index": i
                })
            
            # Extract damage types and areas for union (using NMS-processed predictions)
            for pred in nms_predictions:
                cls = pred.get("class", "")
                if not cls:
                    continue
                
                # class like "bonnet-dent" -> area "bonnet", type "dent"
                parts = cls.split("-")
                if len(parts) == 2:
                    area, d_type = parts
                    combined_areas.append(area.replace("_", " "))
                    combined_damage_types.append(d_type.replace("_", " "))
                else:
                    combined_damage_types.append(cls.replace("_", " "))
                
                # Collect confidence scores
                confidence = pred.get("confidence", 0.0)
                all_confidence_scores.append(confidence)
        
        # Apply cross-image merging and confidence filtering
        merged_predictions = roboflow_service.merge_detections_across_images(all_predictions, iou_threshold=0.3)
        accepted_predictions, review_predictions = roboflow_service.apply_confidence_filtering(merged_predictions)
        
        # Calculate weighted confidence
        confidence_analysis = roboflow_service.calculate_weighted_confidence(accepted_predictions)
        
        # Create combined summary using accepted predictions and weighted confidence
        accepted_confidence_scores = [pred.get("confidence", 0.0) for pred in accepted_predictions]
        combined_summary = {
            "total_detections": len(accepted_predictions),
            "review_detections": len(review_predictions),
            "damage_types": list(set(combined_damage_types)),
            "confidence_scores": accepted_confidence_scores,
            "average_confidence": sum(accepted_confidence_scores) / len(accepted_confidence_scores) if accepted_confidence_scores else 0.0,
            "weighted_confidence": confidence_analysis.get("overall_confidence", 0.0),
            "confidence_band": confidence_analysis.get("confidence_band", "Low"),
            "per_class_confidences": confidence_analysis.get("per_class_confidences", {}),
            "class_weights": confidence_analysis.get("class_weights", {})
        }

        # Build normalized payload compatible with damage report format
        uniq_areas = ", ".join(sorted(set(combined_areas))) if combined_areas else ""
        uniq_types = ", ".join(sorted(set(combined_damage_types))) if combined_damage_types else ""

        # Infer damage side from detected areas
        def infer_damage_side(areas):
            """Infer damage side from detected areas based on Roboflow model class names"""
            if not areas:
                return ""
            
            # Convert to lowercase for comparison
            areas_lower = [area.lower() for area in areas]
            
            # Based on actual Roboflow model class names
            front_indicators = ['bonnet', 'hood', 'bumper', 'headlight', 'grille', 'radiator', 'front']
            rear_indicators = ['boot', 'trunk', 'tailgate', 'taillight', 'rear', 'back', 'tail']
            side_indicators = ['door', 'mirror', 'side', 'wing', 'fender']
            left_indicators = ['left', 'driver', 'nearside']
            right_indicators = ['right', 'passenger', 'offside']
            
            # Check for specific side indicators first
            for area in areas_lower:
                if any(indicator in area for indicator in left_indicators):
                    return "Left"
                if any(indicator in area for indicator in right_indicators):
                    return "Right"
            
            # Check for side areas
            for area in areas_lower:
                if any(indicator in area for indicator in side_indicators):
                    return ""
            
            # Check for front/rear indicators
            for area in areas_lower:
                if any(indicator in area for indicator in front_indicators):
                    return "Front"
                if any(indicator in area for indicator in rear_indicators):
                    return "Rear"
            
            return ""
        
        inferred_damage_side = infer_damage_side(combined_areas)

        # Use weighted confidence for severity calculation
        weighted_conf = combined_summary.get("weighted_confidence", 0.0)
        confidence_percent = int(round(weighted_conf * 100))
        confidence_band = combined_summary.get("confidence_band", "Low")
        
        # Map confidence band to severity
        if confidence_band == "High":
            severity = "High"
        elif confidence_band == "Medium":
            severity = "Medium"
        else:
            severity = "Low"

        # Generate suggested repair action based on combined damage types
        suggested_repair_action = ""
        if combined_damage_types:
            if any("dent" in dt.lower() for dt in combined_damage_types):
                suggested_repair_action = "Repair dents and paint"
            elif any("scratch" in dt.lower() for dt in combined_damage_types):
                suggested_repair_action = "Polish and touch-up paint"
            elif any("crack" in dt.lower() or "break" in dt.lower() for dt in combined_damage_types):
                suggested_repair_action = "Replace damaged parts"
            else:
                suggested_repair_action = "Professional assessment required"

        # Build normalized_report similar to damage report endpoints
        normalized_report = {
            "client_area_of_damage": uniq_areas,
            "client_unrelated_damage": "",
            "client_vehicle_status_id": None,
            "damage_diagram": {
                "ai_analysis": "comprehensive",
                "confidence": "high" if confidence_percent >= 80 else "medium" if confidence_percent >= 60 else "low",
                "detected_areas": list(set(combined_areas)) or [],
                "detected_types": list(set(combined_damage_types)) or []
            },
            "damage_side": inferred_damage_side,
            "area_of_damage": uniq_areas,
            "type_of_damage": uniq_types,
            "severity": severity,
            "confidence_percent": confidence_percent,
            "total_damaged_points_identified": combined_summary.get("total_detections", 0),
            "suggested_repair_action": suggested_repair_action,
            "vehicle_status_id": None,
            "raw_result": {
                "summary": combined_summary,
            }
        }

        # Prepare images list (matching damage report format)
        images = [
            {"file_path": url, "original_filename": f"image_{i+1}"}
            for i, url in enumerate(request.image_urls)
        ]

        # Prepare response matching damage report format
        response: Dict[str, Any] = {
            "predictions": accepted_predictions,
            "review_predictions": review_predictions,
            "summary": {
                "total_detections": combined_summary.get("total_detections", 0),
                "review_detections": combined_summary.get("review_detections", 0),
                "average_confidence": combined_summary.get("average_confidence", 0.0),
                "weighted_confidence": combined_summary.get("weighted_confidence", 0.0),
                "confidence_band": combined_summary.get("confidence_band", "Low"),
                "per_class_confidences": combined_summary.get("per_class_confidences", {}),
                "class_weights": combined_summary.get("class_weights", {})
            },
            "metadata": {
                "total_images": len(request.image_urls),
                "model_used": roboflow_service.workflow_id,
                "images": image_metadata,
                "processing_stats": {
                    "total_detections": len(all_predictions),
                    "after_nms": len(all_predictions),
                    "after_merging": len(merged_predictions),
                    "accepted": len(accepted_predictions),
                    "review": len(review_predictions)
                }
            },
            "normalized_report": normalized_report,
            "images": images,
            "confidence_analysis": confidence_analysis,
        }

        # Add annotated images if requested
        if request.include_annotated_image and all_annotated_images:
            response["annotated_images"] = all_annotated_images
        
        logger.info(f"Successfully processed car damage detection for {len(request.image_urls)} image URL(s)")
        
        return response
        
    except HTTPException as e:
        logger.error(f"HTTP error in car damage detection from URL: {e.detail}")
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in car damage detection from URL: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred during car damage detection"
        )