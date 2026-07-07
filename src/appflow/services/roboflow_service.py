#original code

# import base64
# import io
# import tempfile
# import os
# import requests
# import numpy as np
# from typing import Dict, Any, Optional, List, Tuple
# from PIL import Image, ImageDraw, ImageFont
# from inference_sdk import InferenceHTTPClient
# from fastapi import HTTPException, UploadFile
# import logging

# logger = logging.getLogger(__name__)

# class RoboflowService:
#     """
#     Service for car damage detection using Roboflow API
#     """
    
#     def __init__(self):
#         self.client = InferenceHTTPClient(
#             api_url="https://serverless.roboflow.com",
#             api_key="RkvXD9M4EfgdqO8D9gdQ"
#         )
#         self.model_id = "car-damage-detection-5ioys/1"
#     # def __init__(self):
#     #     self.client = InferenceHTTPClient(
#     #         api_url="https://serverless.roboflow.com",  # 👈 local server
#     #         api_key="544BE3A8s8Q5xr4aJrTf"
#     #     )

#     #     self.workspace_name = "alis-workspace-r7wfe"
#     #     self.workflow_id = "detect-count-and-visualize"
    
#     def calculate_iou(self, box1: Dict[str, float], box2: Dict[str, float]) -> float:
#         """
#         Calculate Intersection over Union (IoU) between two bounding boxes
        
#         Args:
#             box1: First bounding box with x, y, width, height
#             box2: Second bounding box with x, y, width, height
            
#         Returns:
#             IoU value between 0 and 1
#         """
#         # Convert center coordinates to corner coordinates
#         x1_1 = box1['x'] - box1['width'] / 2
#         y1_1 = box1['y'] - box1['height'] / 2
#         x2_1 = box1['x'] + box1['width'] / 2
#         y2_1 = box1['y'] + box1['height'] / 2
        
#         x1_2 = box2['x'] - box2['width'] / 2
#         y1_2 = box2['y'] - box2['height'] / 2
#         x2_2 = box2['x'] + box2['width'] / 2
#         y2_2 = box2['y'] + box2['height'] / 2
        
#         # Calculate intersection area
#         x1_i = max(x1_1, x1_2)
#         y1_i = max(y1_1, y1_2)
#         x2_i = min(x2_1, x2_2)
#         y2_i = min(y2_1, y2_2)
        
#         if x2_i <= x1_i or y2_i <= y1_i:
#             return 0.0
        
#         intersection_area = (x2_i - x1_i) * (y2_i - y1_i)
        
#         # Calculate union area
#         area1 = box1['width'] * box1['height']
#         area2 = box2['width'] * box2['height']
#         union_area = area1 + area2 - intersection_area
        
#         return intersection_area / union_area if union_area > 0 else 0.0
    
    # def apply_nms_per_image(self, predictions: List[Dict[str, Any]], iou_threshold: float = 0.5) -> List[Dict[str, Any]]:
    #     """
    #     Apply Non-Maximum Suppression (NMS) to remove duplicate detections within a single image
        
    #     Args:
    #         predictions: List of predictions from Roboflow API
    #         iou_threshold: IoU threshold for NMS (default: 0.5)
            
    #     Returns:
    #         List of predictions after NMS
    #     """
    #     if not predictions:
    #         return []
        
    #     # Sort predictions by confidence score (descending)
    #     sorted_predictions = sorted(predictions, key=lambda x: x.get('confidence', 0), reverse=True)
        
    #     # Keep track of which predictions to keep
    #     keep = []
    #     suppressed = set()
        
    #     for i, pred in enumerate(sorted_predictions):
    #         if i in suppressed:
    #             continue
                
    #         keep.append(pred)
            
    #         # Suppress overlapping predictions
    #         for j in range(i + 1, len(sorted_predictions)):
    #             if j in suppressed:
    #                 continue
                    
    #             # Only suppress if same class
    #             if pred.get('class') == sorted_predictions[j].get('class'):
    #                 iou = self.calculate_iou(pred, sorted_predictions[j])
    #                 if iou >= iou_threshold:
    #                     suppressed.add(j)
        
    #     logger.info(f"NMS applied: {len(predictions)} -> {len(keep)} predictions (suppressed {len(suppressed)})")
    #     return keep
    
    # def merge_detections_across_images(self, all_predictions: List[Dict[str, Any]], iou_threshold: float = 0.3) -> List[Dict[str, Any]]:
    #     """
    #     Merge detections across images to create union of unique detections
        
    #     Args:
    #         all_predictions: List of all predictions from all images
    #         iou_threshold: IoU threshold for merging (default: 0.3)
            
    #     Returns:
    #         List of merged unique detections
    #     """
    #     if not all_predictions:
    #         return []
        
    #     # Sort predictions by confidence score (descending)
    #     sorted_predictions = sorted(all_predictions, key=lambda x: x.get('confidence', 0), reverse=True)
        
    #     # Keep track of which predictions to keep
    #     keep = []
    #     merged = set()
        
    #     for i, pred in enumerate(sorted_predictions):
    #         if i in merged:
    #             continue
                
    #         keep.append(pred)
            
    #         # Merge overlapping predictions from other images
    #         for j in range(i + 1, len(sorted_predictions)):
    #             if j in merged:
    #                 continue
                    
    #             # Only merge if same class
    #             if pred.get('class') == sorted_predictions[j].get('class'):
    #                 iou = self.calculate_iou(pred, sorted_predictions[j])
    #                 if iou >= iou_threshold:
    #                     merged.add(j)
        
    #     logger.info(f"Cross-image merging applied: {len(all_predictions)} -> {len(keep)} unique detections (merged {len(merged)})")
    #     return keep
    
    # def apply_confidence_filtering(self, predictions: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    #     """
    #     Apply confidence filtering: ignore < 0.55, flag 0.50-0.55 as review
        
    #     Args:
    #         predictions: List of predictions
            
    #     Returns:
    #         Tuple of (accepted_predictions, review_predictions)
    #     """
    #     accepted = []
    #     review = []
        
    #     for pred in predictions:
    #         confidence = pred.get('confidence', 0.0)
            
    #         if confidence >= 0.55:
    #             accepted.append(pred)
    #         elif confidence >= 0.50:
    #             # Flag for review
    #             pred_copy = pred.copy()
    #             pred_copy['review_flag'] = True
    #             review.append(pred_copy)
    #         # Ignore predictions < 0.50
        
    #     logger.info(f"Confidence filtering: {len(accepted)} accepted, {len(review)} flagged for review, {len(predictions) - len(accepted) - len(review)} ignored")
    #     return accepted, review
    
    # def get_class_weight(self, class_name: str) -> float:
    #     """
    #     Get weight for a specific damage class
        
    #     Args:
    #         class_name: Name of the damage class
            
    #     Returns:
    #         Weight value for the class
    #     """
    #     class_lower = class_name.lower()
        
    #     # Front/Rear Bumper: 1.2
    #     if 'bumper' in class_lower:
    #         return 1.2
        
    #     # Bonnet/Boot: 1.0
    #     if any(part in class_lower for part in ['bonnet', 'boot', 'hood', 'trunk']):
    #         return 1.0
        
    #     # Door/Quarter Panel: 0.9
    #     if any(part in class_lower for part in ['door', 'quarter', 'panel', 'wing', 'fender']):
    #         return 0.9
        
    #     # Roof: 0.8
    #     if 'roof' in class_lower:
    #         return 0.8
        
    #     # Glass/Light Damage: 1.1-1.3
    #     if any(part in class_lower for part in ['glass', 'light', 'headlight', 'taillight', 'mirror']):
    #         return 1.1
        
    #     # Default weight
    #     return 1.0
    
    # def calculate_weighted_confidence(self, predictions: List[Dict[str, Any]]) -> Dict[str, Any]:
    #     """
    #     Calculate weighted confidence per class and overall weighted confidence
        
    #     Args:
    #         predictions: List of predictions
            
    #     Returns:
    #         Dict containing confidence analysis
    #     """
    #     if not predictions:
    #         return {
    #             "overall_confidence": 0.0,
    #             "confidence_band": "Low",
    #             "per_class_confidences": {},
    #             "weighted_average": 0.0,
    #             "total_weight": 0.0,
    #             "class_weights": {}
    #         }
        
    #     # Group predictions by class
    #     class_groups = {}
    #     for pred in predictions:
    #         class_name = pred.get('class', 'unknown')
    #         confidence = pred.get('confidence', 0.0)
            
    #         if class_name not in class_groups:
    #             class_groups[class_name] = []
    #         class_groups[class_name].append(confidence)
        
    #     # Calculate average confidence per class
    #     per_class_confidences = {}
    #     weighted_sum = 0.0
    #     total_weight = 0.0
        
    #     for class_name, confidences in class_groups.items():
    #         avg_confidence = sum(confidences) / len(confidences)
    #         per_class_confidences[class_name] = avg_confidence
            
    #         # Apply weight
    #         weight = self.get_class_weight(class_name)
    #         weighted_sum += avg_confidence * weight
    #         total_weight += weight
        
    #     # Calculate overall weighted confidence
    #     overall_confidence = weighted_sum / total_weight if total_weight > 0 else 0.0
        
    #     # Determine confidence band
    #     if overall_confidence >= 0.85:
    #         confidence_band = "High"
    #     elif overall_confidence >= 0.70:
    #         confidence_band = "Medium"
    #     else:
    #         confidence_band = "Low"
        
    #     return {
    #         "overall_confidence": overall_confidence,
    #         "confidence_band": confidence_band,
    #         "per_class_confidences": per_class_confidences,
    #         "weighted_average": overall_confidence,
    #         "total_weight": total_weight,
    #         "class_weights": {class_name: self.get_class_weight(class_name) for class_name in class_groups.keys()}
    #     }
    
    # def _validate_image_file(self, file: UploadFile) -> None:
    #     """
    #     Validate that the uploaded file is a valid image
    #     """
    #     # Check content type
    #     if not file.content_type or not file.content_type.startswith('image/'):
    #         raise HTTPException(
    #             status_code=400, 
    #             detail="File must be an image (JPEG, PNG, etc.)"
    #         )
        
    #     # Check file extension
    #     allowed_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'}
        
    #     if not file.filename:
    #         raise HTTPException(
    #             status_code=400,
    #             detail="File must have a valid filename"
    #         )
        
    #     # Extract file extension (with dot)
    #     filename_lower = file.filename.lower()
    #     file_extension = None
        
    #     for ext in allowed_extensions:
    #         if filename_lower.endswith(ext):
    #             file_extension = ext
    #             break
        
    #     if not file_extension:
    #         raise HTTPException(
    #             status_code=400,
    #             detail=f"Unsupported image format. Please upload JPEG, PNG, BMP, TIFF, TIF, or WEBP files. Received: {file.filename}"
    #         )
    
#     def _prepare_image_for_api(self, file: UploadFile) -> str:
#         """
#         Prepare uploaded image file for API submission by creating a temporary file
#         """
#         try:
#             # Read the file content
#             file_content = file.file.read()
            
#             # Reset file pointer for potential reuse
#             file.file.seek(0)
            
#             # Create a temporary file
#             temp_fd, temp_path = tempfile.mkstemp(suffix='.jpg')
            
#             try:
#                 # Write the file content to temporary file
#                 with os.fdopen(temp_fd, 'wb') as temp_file:
#                     temp_file.write(file_content)
                
#                 logger.info(f"Image prepared for API. Size: {len(file_content)} bytes, Temp file: {temp_path}")
                
#                 return temp_path
                
#             except Exception as e:
#                 # Clean up temp file if something goes wrong
#                 os.unlink(temp_path)
#                 raise e
            
#         except Exception as e:
#             logger.error(f"Error preparing image for API: {str(e)}")
#             raise HTTPException(
#                 status_code=500,
#                 detail="Failed to process the uploaded image"
#             )
    
#     def _validate_image_dimensions(self, file: UploadFile) -> None:
#         """
#         Validate image dimensions to ensure it's not too large
#         """
#         try:
#             # Read image to check dimensions
#             file_content = file.file.read()
#             file.file.seek(0)  # Reset file pointer
            
#             # Open image with PIL
#             image = Image.open(io.BytesIO(file_content))
#             width, height = image.size
            
#             # Check if image is too large (limit to 10MP)
#             max_pixels = 10 * 1024 * 1024  # 10 megapixels
#             if width * height > max_pixels:
#                 raise HTTPException(
#                     status_code=400,
#                     detail="Image is too large. Please upload an image smaller than 10 megapixels."
#                 )
            
#             # Check minimum dimensions
#             min_dimension = 50
#             if width < min_dimension or height < min_dimension:
#                 raise HTTPException(
#                     status_code=400,
#                     detail="Image is too small. Please upload an image with dimensions at least 50x50 pixels."
#                 )
                
#         except HTTPException:
#             raise
#         except Exception as e:
#             logger.error(f"Error validating image dimensions: {str(e)}")
#             raise HTTPException(
#                 status_code=500,
#                 detail="Failed to validate image dimensions"
#             )
    
#     async def detect_car_damage(self, file: UploadFile, include_annotated_image: bool = False) -> Dict[str, Any]:
#         """
#         Detect car damage in the uploaded image using Roboflow API
        
#         Args:
#             file: Uploaded image file
#             include_annotated_image: Whether to include an annotated image with bounding boxes
            
#         Returns:
#             Dict containing detection results from Roboflow API
            
#         Raises:
#             HTTPException: If image validation fails or API call fails
#         """
#         temp_file_path = None
#         try:
#             # Validate the uploaded file
#             self._validate_image_file(file)
#             self._validate_image_dimensions(file)
            
#             # Prepare image for API (creates temporary file)
#             temp_file_path = self._prepare_image_for_api(file)
            
#             logger.info(f"Processing car damage detection for file: {file.filename}")
            
#             # Call Roboflow API with temporary file path
#             result = self.client.infer(temp_file_path, model_id=self.model_id)
            
#             logger.info(f"Roboflow API response received for file: {file.filename}")
            
#             # Validate API response
#             if not isinstance(result, dict):
#                 raise HTTPException(
#                     status_code=500,
#                     detail="Invalid response from car damage detection service"
#                 )
            
#             # Create annotated image if requested
#             if include_annotated_image:
#                 try:
#                     annotated_image = self.create_highlighted_image(temp_file_path, result)
#                     result['annotated_image'] = annotated_image
#                 except Exception as e:
#                     logger.warning(f"Failed to create annotated image: {str(e)}")
#                     # Continue without annotated image rather than failing the entire request
            
#             return result
            
#         except HTTPException:
#             raise
#         except Exception as e:
#             logger.error(f"Error in car damage detection: {str(e)}")
#             raise HTTPException(
#                 status_code=500,
#                 detail=f"Car damage detection failed: {str(e)}"
#             )
#         finally:
#             # Clean up temporary file
#             if temp_file_path and os.path.exists(temp_file_path):
#                 try:
#                     os.unlink(temp_file_path)
#                     logger.info(f"Cleaned up temporary file: {temp_file_path}")
#                 except Exception as e:
#                     logger.warning(f"Failed to clean up temporary file {temp_file_path}: {str(e)}")
    
#     def get_damage_summary(self, detection_result: Dict[str, Any]) -> Dict[str, Any]:
#         """
#         Extract and summarize damage information from detection results
        
#         Args:
#             detection_result: Raw result from Roboflow API
            
#         Returns:
#             Dict containing summarized damage information
#         """
#         try:
#             summary = {
#                 "total_detections": 0,
#                 "damage_types": [],
#                 "confidence_scores": [],
#                 "bounding_boxes": []
#             }
            
#             # Extract predictions if available
#             predictions = detection_result.get("predictions", [])
#             summary["total_detections"] = len(predictions)
            
#             for prediction in predictions:
#                 # Extract class (damage type)
#                 class_name = prediction.get("class", "Unknown")
#                 summary["damage_types"].append(class_name)
                
#                 # Extract confidence score
#                 confidence = prediction.get("confidence", 0.0)
#                 summary["confidence_scores"].append(confidence)
                
#                 # Extract bounding box coordinates
#                 bbox = prediction.get("bbox", {})
#                 if bbox:
#                     summary["bounding_boxes"].append({
#                         "x": bbox.get("x"),
#                         "y": bbox.get("y"),
#                         "width": bbox.get("width"),
#                         "height": bbox.get("height")
#                     })
            
#             # Calculate average confidence
#             if summary["confidence_scores"]:
#                 summary["average_confidence"] = sum(summary["confidence_scores"]) / len(summary["confidence_scores"])
#             else:
#                 summary["average_confidence"] = 0.0
            
#             return summary
            
#         except Exception as e:
#             logger.error(f"Error creating damage summary: {str(e)}")
#             return {
#                 "error": "Failed to process detection results",
#                 "total_detections": 0,
#                 "damage_types": [],
#                 "confidence_scores": [],
#                 "bounding_boxes": []
#             }
    
#     def create_highlighted_image(self, image_path: str, detection_result: Dict[str, Any]) -> str:
#         """
#         Create a highlighted image with bounding boxes around detected damage areas
        
#         Args:
#             image_path: Path to the original image
#             detection_result: Detection results from Roboflow API
            
#         Returns:
#             Base64 encoded string of the highlighted image
#         """
#         try:
#             # Open the original image
#             image = Image.open(image_path)
#             draw = ImageDraw.Draw(image)
            
#             # Get image dimensions
#             img_width, img_height = image.size
            
#             # Define colors for different damage types
#             damage_colors = {
#                 'bonnet-dent': '#FF0000',      # Red
#                 'door-dent': '#00FF00',        # Green
#                 'bumper-damage': '#0000FF',    # Blue
#                 'scratch': '#FFFF00',          # Yellow
#                 'broken-glass': '#FF00FF',     # Magenta
#                 'headlight-damage': '#00FFFF', # Cyan
#                 'tail-light-damage': '#FFA500', # Orange
#                 'side-mirror-damage': '#800080' # Purple
#             }
            
#             # Get predictions
#             predictions = detection_result.get('predictions', [])
            
#             for i, prediction in enumerate(predictions):
#                 # Extract bounding box coordinates
#                 x = prediction.get('x', 0)
#                 y = prediction.get('y', 0)
#                 width = prediction.get('width', 0)
#                 height = prediction.get('height', 0)
#                 confidence = prediction.get('confidence', 0)
#                 class_name = prediction.get('class', 'unknown')
                
#                 # Calculate bounding box coordinates
#                 x1 = x - width / 2
#                 y1 = y - height / 2
#                 x2 = x + width / 2
#                 y2 = y + height / 2
                
#                 # Get color for this damage type
#                 color = damage_colors.get(class_name, '#FF0000')  # Default to red
                
#                 # Draw bounding box
#                 draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
                
#                 # Draw label background
#                 label_text = f"{class_name}: {confidence:.2f}"
                
#                 # Try to load a font, fallback to default if not available
#                 try:
#                     font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 16)
#                 except:
#                     try:
#                         font = ImageFont.load_default()
#                     except:
#                         font = None
                
#                 # Get text size
#                 if font:
#                     bbox = draw.textbbox((0, 0), label_text, font=font)
#                     text_width = bbox[2] - bbox[0]
#                     text_height = bbox[3] - bbox[1]
#                 else:
#                     text_width = len(label_text) * 6
#                     text_height = 12
                
#                 # Draw label background
#                 label_y = max(y1 - text_height - 5, 0)
#                 draw.rectangle([x1, label_y, x1 + text_width + 10, label_y + text_height + 5], 
#                               fill=color, outline=color)
                
#                 # Draw label text
#                 draw.text((x1 + 5, label_y + 2), label_text, fill='white', font=font)
            
#             # Convert image to base64 data URL
#             buffer = io.BytesIO()
#             image.save(buffer, format='JPEG', quality=85)
#             image_data = buffer.getvalue()
#             base64_string = base64.b64encode(image_data).decode('utf-8')
#             data_url = f"data:image/jpeg;base64,{base64_string}"
            
#             logger.info(f"Created highlighted image with {len(predictions)} damage detections")
            
#             return data_url
            
#         except Exception as e:
#             logger.error(f"Error creating highlighted image: {str(e)}")
#             raise HTTPException(
#                 status_code=500,
#                 detail="Failed to create highlighted image"
#             )
    
#     async def detect_car_damage_from_url(self, image_url: str, include_annotated_image: bool = False) -> Dict[str, Any]:
#         """
#         Detect car damage from an image URL using Roboflow API
        
#         Args:
#             image_url: URL of the image to analyze
#             include_annotated_image: Whether to include an annotated image with bounding boxes
            
#         Returns:
#             Dict containing detection results from Roboflow API
            
#         Raises:
#             HTTPException: If URL is invalid or API call fails
#         """
#         temp_file_path = None
#         try:
#             logger.info(f"Processing car damage detection from URL: {image_url}")
            
#             # Download image from URL
#             try:
#                 response = requests.get(image_url, timeout=10)
#                 response.raise_for_status()
#                 image_content = response.content
#             except requests.exceptions.RequestException as e:
#                 logger.error(f"Failed to download image from URL: {str(e)}")
#                 raise HTTPException(
#                     status_code=400,
#                     detail=f"Failed to download image from URL: {str(e)}"
#                 )
            
#             # Validate it's an image
#             try:
#                 image = Image.open(io.BytesIO(image_content))
#                 width, height = image.size
                
#                 # Check dimensions
#                 max_pixels = 10 * 1024 * 1024
#                 if width * height > max_pixels:
#                     raise HTTPException(
#                         status_code=400,
#                         detail="Image is too large. Maximum 10 megapixels."
#                     )
                
#                 min_dimension = 50
#                 if width < min_dimension or height < min_dimension:
#                     raise HTTPException(
#                         status_code=400,
#                         detail="Image is too small. Minimum 50x50 pixels."
#                     )
                    
#             except HTTPException:
#                 raise
#             except Exception as e:
#                 logger.error(f"Invalid image from URL: {str(e)}")
#                 raise HTTPException(
#                     status_code=400,
#                     detail="URL does not contain a valid image"
#                 )
            
#             # Create temporary file for Roboflow API
#             temp_fd, temp_file_path = tempfile.mkstemp(suffix='.jpg')
#             try:
#                 with os.fdopen(temp_fd, 'wb') as temp_file:
#                     temp_file.write(image_content)
                
#                 logger.info(f"Image downloaded and saved. Size: {len(image_content)} bytes")
                
#                 # Call Roboflow API with temporary file path
#                 result = self.client.infer(temp_file_path, model_id=self.model_id)
                
#                 logger.info(f"Roboflow API response received for URL: {image_url}")
                
#                 # Validate API response
#                 if not isinstance(result, dict):
#                     raise HTTPException(
#                         status_code=500,
#                         detail="Invalid response from car damage detection service"
#                     )
                
#                 # Create annotated image if requested
#                 if include_annotated_image:
#                     try:
#                         annotated_image = self.create_highlighted_image(temp_file_path, result)
#                         result['annotated_image'] = annotated_image
#                     except Exception as e:
#                         logger.warning(f"Failed to create annotated image: {str(e)}")
                
#                 return result
                
#             except HTTPException:
#                 raise
#             except Exception as e:
#                 logger.error(f"Error processing image from URL: {str(e)}")
#                 raise HTTPException(
#                     status_code=500,
#                     detail=f"Car damage detection failed: {str(e)}"
#                 )
            
#         finally:
#             # Clean up temporary file
#             if temp_file_path and os.path.exists(temp_file_path):
#                 try:
#                     os.unlink(temp_file_path)
#                     logger.info(f"Cleaned up temporary file: {temp_file_path}")
#                 except Exception as e:
#                     logger.warning(f"Failed to clean up temporary file: {str(e)}")

#original code end


#new code
# import base64
# import io
# import tempfile
# import os
# from typing import Dict, Any, List, Tuple
# from PIL import Image, ImageDraw
# from inference_sdk import InferenceHTTPClient
# from fastapi import UploadFile, HTTPException
# import logging
# import hashlib

# logger = logging.getLogger(__name__)

# class RoboflowService:
    
#     def __init__(self):
#         self.client = InferenceHTTPClient(
#             api_url="https://serverless.roboflow.com",
#             api_key="uPB6ybjYzQVCCTVNXrHC"
#         )

#         self.workspace = "marwas-workspace-sogsw"
#         self.workflow_id = "detect-count-and-visualize"
   

#     def normalize_prediction(self, pred: Dict[str, Any]) -> Dict[str, Any]:
#         raw_class_name = (pred.get("class") or "").strip().lower()
#         class_name = raw_class_name.replace("_", "-")
#         parts = [p for p in class_name.split("-") if p]

#         side = "Unknown"
#         part = ""
#         damage = ""

#         if not parts:
#             return {
#                 **pred,
#                 "side": "Unknown",
#                 "part": "Unknown",
#                 "damage_type": "Damage",
#             }

#         if parts[0] == "windshield":
#             side = "Front"
#             part = "Windshield"
#             damage = parts[-1].title()

#         elif len(parts) >= 2 and parts[0] == "rear" and parts[1] == "glass":
#             side = "Rear"
#             part = "Rear Glass"
#             damage = parts[-1].title()

#         elif parts[0] == "headlight":
#             side = "Front"
#             part = "Headlight"
#             damage = parts[-1].title()

#         elif parts[0] == "taillight":
#             side = "Rear"
#             part = "Taillight"
#             damage = parts[-1].title()

#         elif parts[0] == "hood":
#             side = "Front"
#             part = "Hood"
#             damage = parts[-1].title()

#         elif parts[0] == "trunk":
#             side = "Rear"
#             part = "Trunk"
#             damage = parts[-1].title()

#         elif parts[0] in ["nearside", "offside"]:
#             side_base = "Nearside" if parts[0] == "nearside" else "Offside"

#             if len(parts) >= 4 and parts[1] in ["front", "middle", "rear"]:
#                 side = f"{side_base} {parts[1].title()}"
#                 part = " ".join(parts[2:-1]).title()
#                 damage = parts[-1].title()
#             else:
#                 side = f"{side_base} Front"
#                 part = " ".join(parts[1:-1]).title()
#                 damage = parts[-1].title()

#         elif parts[0] in ["front", "rear", "roof"]:
#             side = parts[0].title()
#             part = " ".join(parts[1:-1]).title() if len(parts) > 2 else parts[0].title()
#             damage = parts[-1].title()

#         else:
#             part = " ".join(parts[:-1]).title() if len(parts) > 1 else parts[0].title()
#             damage = parts[-1].title() if len(parts) > 1 else "Damage"

#         return {
#             **pred,
#             "class": class_name,
#             "side": side,
#             "part": part,
#             "damage_type": damage,
#         }


#     def calculate_severity(self, pred: Dict[str, Any]) -> str:
#         area = pred.get("width", 0) * pred.get("height", 0)
#         damage_type = (pred.get("damage_type") or "").lower()
#         confidence = pred.get("confidence", 0)

#         if damage_type in ["broken", "crash", "shattered"]:
#             return "High"

#         if damage_type in ["dent"]:
#             return "Medium"

#         if area > 20000:
#             severity = "High"
#         elif area > 5000:
#             severity = "Medium"
#         else:
#             severity = "Low"

#         if confidence < 0.6:
#             severity = "Low"

#         return severity

#     # ---------------- COLOR ---------------- #

#     def class_to_color(self, severity: str) -> str:
#         """Return a specific color based on the damage severity"""
        
#         # Normalize input to title case to match your calculate_severity output
#         status = severity.title() if severity else "High"

#         if status == "Low":
#             return "#22C55E"  # Success Green (Tailwind green-500)
#         elif status == "Medium":
#             return "#F59E0B"  # Amber/Orange (Tailwind amber-500)
#         else:
#             return "#EF4444"  # Critical Red (Tailwind red-500)

#         # # Hash the class name
#         # h = int(hashlib.md5(class_name.encode()).hexdigest()[:6], 16)
#         # r = (h >> 16) & 0xFF
#         # g = (h >> 8) & 0xFF
#         # b = h & 0xFF
#         # return f"#{r:02X}{g:02X}{b:02X}"


#     async def detect_car_damage(self, file: UploadFile, include_annotated_image=False,image_index: int = 0):

#         temp_path = None

#         try:
#             content = await file.read()

#             fd, temp_path = tempfile.mkstemp(suffix=".jpg")
#             with os.fdopen(fd, "wb") as f:
#                 f.write(content)

#             # 🔥 WORKFLOW CALL
#             result = self.client.run_workflow(
#                 workspace_name=self.workspace,
#                 workflow_id=self.workflow_id,
#                 images={"image": temp_path},
#                 use_cache=True
#             )
#             print(result)

#             # ⚠️ IMPORTANT: workflow output structure
#             predictions = []

#             predictions = self.extract_predictions(result)
#             print("Image index is :", image_index)

#             # APPLY PIPELINE
#             nms_predictions = self.apply_nms_per_image(predictions,image_index)
#             merged_predictions = self.merge_detections_across_images(nms_predictions)
#             accepted_predictions, review_predictions = self.apply_confidence_filtering(merged_predictions)
#             confidence_analysis = self.calculate_weighted_confidence(accepted_predictions)

#             processed = []
#             for p in accepted_predictions:
#                 norm = self.normalize_prediction(p)
#                 norm["severity"] = self.calculate_severity(norm)
#                 norm["points"] = 1
#                 # norm["image_index"]= image_index
#                 processed.append(norm)

#             response = {
#                 "predictions": processed,
#                 "review_predictions": review_predictions,
#                 "confidence_analysis": confidence_analysis,
#                 "count": len(processed)
#             }
            

#             if include_annotated_image:
#                 response["annotated_image"] = self.create_image(temp_path, processed)

#             return response

#         except Exception as e:
#             logger.error(str(e))
#             raise HTTPException(status_code=500, detail=str(e))

#         finally:
#             if temp_path and os.path.exists(temp_path):
#                 os.remove(temp_path)

#     def create_image_bytes(self, image_path, predictions):
#         from PIL import Image, ImageDraw, ImageFont
#         import io

#         image = Image.open(image_path).convert("RGB")
#         draw = ImageDraw.Draw(image)

#         try:
#             font = ImageFont.truetype("arial.ttf", 18)
#         except:
#             font = ImageFont.load_default()

#         for p in predictions:
#             x, y = p["x"], p["y"]
#             w, h = p["width"], p["height"]

#             x1, y1 = x - w / 2, y - h / 2
#             x2, y2 = x + w / 2, y + h / 2

#             color = self.class_to_color(p["severity"])

#             draw.rectangle([x1, y1, x2, y2], outline=color, width=2)

#             conf_val = int(round(p.get("confidence", 0) * 100))
#             label_text = f"{p['part']} {p['damage_type']} {conf_val}%"

#             t_left, t_top, t_right, t_bottom = draw.textbbox((0, 0), label_text, font=font)
#             text_w = t_right - t_left
#             text_h = t_bottom - t_top

#             padding = 4
#             pill_x1 = x1
#             pill_y1 = max(0, y1 - text_h - (padding * 2))
#             pill_x2 = x1 + text_w + (padding * 2)
#             pill_y2 = y1

#             draw.rectangle([pill_x1, pill_y1, pill_x2, pill_y2], fill=color)
#             draw.text((pill_x1 + padding, pill_y1 + padding), label_text, fill="white", font=font)

#         buffer = io.BytesIO()
#         image.save(buffer, format="JPEG", quality=90)
#         return buffer.getvalue()

#     # ---------------- IMAGE ---------------- #

#     def create_image(self, image_path, predictions):
#         from PIL import Image, ImageDraw, ImageFont

#         image = Image.open(image_path).convert("RGB")
#         draw = ImageDraw.Draw(image)
        
#         # Try to load a default font, fallback to basic if not found
#         try:
#             # Increase size for better readability on high-res car photos
#             font = ImageFont.truetype("arial.ttf", 18)
#         except:
#             font = ImageFont.load_default()

#         for p in predictions:
#             x, y = p["x"], p["y"]
#             w, h = p["width"], p["height"]

#             # Calculate coordinates
#             x1, y1 = x - w/2, y - h/2
#             x2, y2 = x + w/2, y + h/2
#             print(p["class"])
#             color = self.class_to_color(p["severity"])
            
#             # 1. Draw the Bounding Box
#             draw.rectangle([x1, y1, x2, y2], outline=color, width=1)

#             # 2. Prepare the Label Text
#             # We'll use the class and confidence to mimic the first image
#             conf_val = int(round(p.get("confidence", 0) * 100))
#             label_text = f"{p['class']} {conf_val}%"

#             # 3. Calculate Pill Dimensions dynamically
#             # Get text size: (left, top, right, bottom)
#             t_left, t_top, t_right, t_bottom = draw.textbbox((0, 0), label_text, font=font)
#             text_w = t_right - t_left
#             text_h = t_bottom - t_top

#             padding = 4
#             # Position the pill so its BOTTOM edge touches the TOP of the bounding box
#             pill_x1 = x1
#             pill_y1 = y1 - text_h - (padding * 2)
#             pill_x2 = x1 + text_w + (padding * 2)
#             pill_y2 = y1

#             # 4. Draw Pill Background and Text
#             # Draw the background "pill"
#             draw.rectangle([pill_x1, pill_y1, pill_x2, pill_y2], fill=color)

#             # Draw the text centered in that pill
#             draw.text((pill_x1 + padding, pill_y1 + padding), label_text, fill="white", font=font)

#         # Save to base64
#         buffer = io.BytesIO()
#         image.save(buffer, format="JPEG", quality=90)
#         return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()
#     # ---------------- EXTRACT PREDICTIONS ---------------- #
#     def extract_predictions(self, workflow_result):
#         try:
#             # Step 1: unwrap list
#             if isinstance(workflow_result, list) and len(workflow_result) > 0:
#                 workflow_result = workflow_result[0]

#             if not isinstance(workflow_result, dict):
#                 return []

#             preds = []

#             # ✅ CASE 1: predictions is a LIST
#             if isinstance(workflow_result.get("predictions"), list):
#                 preds = workflow_result["predictions"]

#             # ✅ CASE 2: predictions is a DICT (YOUR CASE)
#             elif isinstance(workflow_result.get("predictions"), dict):
#                 inner = workflow_result["predictions"]

#                 if isinstance(inner.get("predictions"), list):
#                     preds = inner["predictions"]

#             # ✅ CASE 3: nested under output
#             elif isinstance(workflow_result.get("output"), dict):
#                 output = workflow_result["output"]

#                 if isinstance(output.get("predictions"), list):
#                     preds = output["predictions"]

#             # Final safety filter
#             print("RAW RESULT:", workflow_result)
#             print("EXTRACTED PREDICTIONS:", preds)
#             return [p for p in preds if isinstance(p, dict)]

#         except Exception as e:
#             logger.error(f"Prediction extraction failed: {e}")
#             return []
        
#     def apply_nms_per_image(self, predictions: List[Dict[str, Any]], image_index:int, iou_threshold: float = 0.5) -> List[Dict[str, Any]]:
#         """
#         Apply Non-Maximum Suppression (NMS) to remove duplicate detections within a single image
        
#         Args:
#             predictions: List of predictions from Roboflow API
#             iou_threshold: IoU threshold for NMS (default: 0.5)
            
#         Returns:
#             List of predictions after NMS
#         """
#         print(image_index)
#         if not predictions:
#             return []
        
#         # Sort predictions by confidence score (descending)
#         sorted_predictions = sorted(predictions, key=lambda x: x.get('confidence', 0), reverse=True)
#         print(sorted_predictions)
#         # Keep track of which predictions to keep
#         keep = []
#         suppressed = set()
        
#         for i, pred in enumerate(sorted_predictions):
#             if "image_index" not in pred:
#                 pred["image_index"] = image_index  # default 0 if missing

#             if i in suppressed:
#                 continue
                
#             keep.append(pred)
            
#             # Suppress overlapping predictions
#             for j in range(i + 1, len(sorted_predictions)):
#                 if j in suppressed:
#                     continue
                    
#                 # Only suppress if same class
#                 if pred.get('class') == sorted_predictions[j].get('class'):
#                     iou = self.calculate_iou(pred, sorted_predictions[j])
#                     if iou >= iou_threshold:
#                         suppressed.add(j)
        
#         logger.info(f"NMS applied: {len(predictions)} -> {len(keep)} predictions (suppressed {len(suppressed)})")
#         return keep
    
#     def merge_detections_across_images(self, all_predictions: List[Dict[str, Any]], iou_threshold: float = 0.3) -> List[Dict[str, Any]]:
#         """
#         Merge detections across images to create union of unique detections
        
#         Args:
#             all_predictions: List of all predictions from all images
#             iou_threshold: IoU threshold for merging (default: 0.3)
            
#         Returns:
#             List of merged unique detections
#         """
#         if not all_predictions:
#             return []
        
#         # Sort predictions by confidence score (descending)
#         sorted_predictions = sorted(all_predictions, key=lambda x: x.get('confidence', 0), reverse=True)
        
#         # Keep track of which predictions to keep
#         keep = []
#         merged = set()
        
#         for i, pred in enumerate(sorted_predictions):
#             if i in merged:
#                 continue
                
#             keep.append(pred)
            
#             # Merge overlapping predictions from other images
#             for j in range(i + 1, len(sorted_predictions)):
#                 if j in merged:
#                     continue
                    
#                 # Only merge if same class
#                 if pred.get('class') == sorted_predictions[j].get('class'):
#                     iou = self.calculate_iou(pred, sorted_predictions[j])
#                     if iou >= iou_threshold:
#                         merged.add(j)
        
#         logger.info(f"Cross-image merging applied: {len(all_predictions)} -> {len(keep)} unique detections (merged {len(merged)})")
#         return keep
    
#     def apply_confidence_filtering(self, predictions: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
#         """
#         Apply confidence filtering: ignore < 0.55, flag 0.50-0.55 as review
        
#         Args:
#             predictions: List of predictions
            
#         Returns:
#             Tuple of (accepted_predictions, review_predictions)
#         """
#         accepted = []
#         review = []
        
#         for pred in predictions:
#             confidence = pred.get('confidence', 0.0)
            
#             if confidence >= 0.55:
#                 accepted.append(pred)
#             elif confidence >= 0.50:
#                 # Flag for review
#                 pred_copy = pred.copy()
#                 pred_copy['review_flag'] = True
#                 review.append(pred_copy)
#             # Ignore predictions < 0.50
        
#         logger.info(f"Confidence filtering: {len(accepted)} accepted, {len(review)} flagged for review, {len(predictions) - len(accepted) - len(review)} ignored")
#         return accepted, review
    
#     def get_class_weight(self, class_name: str) -> float:
#         """
#         Get weight for a specific damage class
        
#         Args:
#             class_name: Name of the damage class
            
#         Returns:
#             Weight value for the class
#         """
#         class_lower = class_name.lower()
        
#         # Front/Rear Bumper: 1.2
#         if 'bumper' in class_lower:
#             return 1.2
        
#         # Bonnet/Boot: 1.0
#         if any(part in class_lower for part in ['bonnet', 'boot', 'hood', 'trunk']):
#             return 1.0
        
#         # Door/Quarter Panel: 0.9
#         if any(part in class_lower for part in ['door', 'quarter', 'panel', 'wing', 'fender']):
#             return 0.9
        
#         # Roof: 0.8
#         if 'roof' in class_lower:
#             return 0.8
        
#         # Glass/Light Damage: 1.1-1.3
#         if any(part in class_lower for part in ['glass', 'light', 'headlight', 'taillight', 'mirror']):
#             return 1.1
        
#         # Default weight
#         return 1.0
    
#     def calculate_weighted_confidence(self, predictions: List[Dict[str, Any]]) -> Dict[str, Any]:
#         """
#         Calculate weighted confidence per class and overall weighted confidence
        
#         Args:
#             predictions: List of predictions
            
#         Returns:
#             Dict containing confidence analysis
#         """
#         if not predictions:
#             return {
#                 "overall_confidence": 0.0,
#                 "confidence_band": "Low",
#                 "per_class_confidences": {},
#                 "weighted_average": 0.0,
#                 "total_weight": 0.0,
#                 "class_weights": {},
#                 "high_severity_count": 0
#             }
        
#         # Group predictions by class
#         class_groups = {}
#         high_severity_count= 0
#         for pred in predictions:
#             class_name = pred.get('class', 'unknown')
#             confidence = pred.get('confidence', 0.0)
#             severity= pred.get('severity','').capitalize()
#             if severity=="High":
#                 high_severity_count += 1
#             if class_name not in class_groups:
#                 class_groups[class_name] = []
#             class_groups[class_name].append(confidence)
        
#         # Calculate average confidence per class
#         per_class_confidences = {}
#         weighted_sum = 0.0
#         total_weight = 0.0
        
#         for class_name, confidences in class_groups.items():
#             avg_confidence = sum(confidences) / len(confidences)
#             per_class_confidences[class_name] = avg_confidence
            
#             # Apply weight
#             weight = self.get_class_weight(class_name)
#             weighted_sum += avg_confidence * weight
#             total_weight += weight
        
#         # Calculate overall weighted confidence
#         overall_confidence = weighted_sum / total_weight if total_weight > 0 else 0.0
        
#         # Determine confidence band
#         if overall_confidence >= 0.85:
#             confidence_band = "High"
#         elif overall_confidence >= 0.70:
#             confidence_band = "Medium"
#         else:
#             confidence_band = "Low"
        
#         return {
#             "overall_confidence": overall_confidence,
#             "confidence_band": confidence_band,
#             "per_class_confidences": per_class_confidences,
#             "weighted_average": overall_confidence,
#             "total_weight": total_weight,
#             "class_weights": {class_name: self.get_class_weight(class_name) for class_name in class_groups.keys()},
#             "high_severity_count": high_severity_count
#         }
    
#     def calculate_iou(self, box1, box2):
#         x1_1 = box1['x'] - box1['width'] / 2
#         y1_1 = box1['y'] - box1['height'] / 2
#         x2_1 = box1['x'] + box1['width'] / 2
#         y2_1 = box1['y'] + box1['height'] / 2

#         x1_2 = box2['x'] - box2['width'] / 2
#         y1_2 = box2['y'] - box2['height'] / 2
#         x2_2 = box2['x'] + box2['width'] / 2
#         y2_2 = box2['y'] + box2['height'] / 2

#         x1_i = max(x1_1, x1_2)
#         y1_i = max(y1_1, y1_2)
#         x2_i = min(x2_1, x2_2)
#         y2_i = min(y2_1, y2_2)

#         if x2_i <= x1_i or y2_i <= y1_i:
#             return 0.0

#         intersection = (x2_i - x1_i) * (y2_i - y1_i)
#         union = box1['width'] * box1['height'] + box2['width'] * box2['height'] - intersection

#         return intersection / union if union > 0 else 0.0
# # singleton
# roboflow_service = RoboflowService()


import base64
import io
import logging
import os
import tempfile
from typing import Any, Dict, List, Tuple

from fastapi import HTTPException, UploadFile
from inference_sdk import InferenceHTTPClient
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

# Markers that a failure is the Roboflow inference host being unreachable
# (DNS/network/timeout) rather than a genuine processing bug.
_CONNECTIVITY_MARKERS = (
    "could not connect",
    "max retries",
    "nameresolution",
    "failed to resolve",
    "connection",
    "timed out",
    "timeout",
    "retryerror",
    "temporarily unavailable",
)


def _is_connectivity_error(message: str) -> bool:
    lowered = (message or "").lower()
    return any(marker in lowered for marker in _CONNECTIVITY_MARKERS)


_UNREACHABLE_DETAIL = (
    "The vehicle damage analysis service is temporarily unreachable. "
    "Please check your connection and try again in a moment."
)


class RoboflowService:
    def __init__(self):
        # Config is env-driven (see .env). The fallbacks keep existing behaviour
        # working if the vars are unset; the API key should live only in .env.
        self.api_url = os.getenv("ROBOFLOW_API_URL", "https://serverless.roboflow.com")
        # NOTE: this key was previously hard-coded and committed — rotate it.
        self.api_key = os.getenv("ROBOFLOW_API_KEY", "uPB6ybjYzQVCCTVNXrHC")
        self.client = InferenceHTTPClient(api_url=self.api_url, api_key=self.api_key)

        self.workspace = os.getenv("ROBOFLOW_WORKSPACE", "marwas-workspace-sogsw")
        # Public "Detect, Count, and Visualize 3" workflow.
        self.workflow_id = os.getenv("ROBOFLOW_WORKFLOW_ID", "detect-count-and-visualize-3")

    def health_check(self) -> Dict[str, Any]:
        """Confirm the configured inference server is reachable. Use this after
        pointing ROBOFLOW_API_URL at a self-hosted server (e.g. http://localhost:9001)
        to verify the backend can talk to it. Any HTTP response counts as 'up'."""
        import urllib.request
        import urllib.error

        host = (self.api_url or "").lower()
        info: Dict[str, Any] = {
            "api_url": self.api_url,
            "workspace": self.workspace,
            "workflow_id": self.workflow_id,
            "self_hosted": ("localhost" in host or "127.0.0.1" in host
                            or not host.startswith("https://serverless.roboflow.com")),
        }
        try:
            with urllib.request.urlopen(self.api_url, timeout=5) as resp:
                info["reachable"] = True
                info["status_code"] = getattr(resp, "status", 200)
        except urllib.error.HTTPError as exc:
            info["reachable"] = True  # server answered (even with an error) → it's up
            info["status_code"] = exc.code
        except Exception as exc:  # noqa: BLE001 — surface any connection failure
            info["reachable"] = False
            info["error"] = str(exc)
        return info

    def normalize_prediction(self, pred: Dict[str, Any]) -> Dict[str, Any]:
        raw_class_name = (pred.get("class") or "").strip().lower()
        class_name = raw_class_name.replace("_", "-")
        parts = [p for p in class_name.split("-") if p]

        side = "Unknown"
        part = ""
        damage = ""

        if not parts:
            return {
                **pred,
                "class": class_name,
                "side": "Unknown",
                "part": "Unknown",
                "damage_type": "Damage",
            }

        # Special absolute/front/rear mappings
        if parts[0] == "windshield":
            side = "Front"
            part = "Windshield"
            damage = parts[-1].title()

        elif len(parts) >= 2 and parts[0] == "rear" and parts[1] == "glass":
            side = "Rear"
            part = "Rear Glass"
            damage = parts[-1].title()

        elif parts[0] == "headlight":
            side = "Front"
            part = "Headlight"
            damage = parts[-1].title()

        elif parts[0] == "taillight":
            side = "Rear"
            part = "Taillight"
            damage = parts[-1].title()

        elif parts[0] == "hood":
            side = "Front"
            part = "Hood"
            damage = parts[-1].title()

        elif parts[0] == "trunk":
            side = "Rear"
            part = "Trunk"
            damage = parts[-1].title()

        # Nearside / Offside classes
        elif parts[0] in ["nearside", "offside"]:
            side_base = "Nearside" if parts[0] == "nearside" else "Offside"

            # e.g. offside-front-door-broken
            if len(parts) >= 4 and parts[1] in ["front", "middle", "rear"]:
                side = f"{side_base} {parts[1].title()}"
                part = " ".join(parts[2:-1]).title()
                damage = parts[-1].title()
            else:
                # e.g. nearside-mirror-broken
                side = f"{side_base} Front"
                part = " ".join(parts[1:-1]).title()
                damage = parts[-1].title()

        # Front / Rear / Roof classes
        elif parts[0] in ["front", "rear", "roof"]:
            side = parts[0].title()
            part = " ".join(parts[1:-1]).title() if len(parts) > 2 else parts[0].title()
            damage = parts[-1].title()

        else:
            part = " ".join(parts[:-1]).title() if len(parts) > 1 else parts[0].title()
            damage = parts[-1].title() if len(parts) > 1 else "Damage"

        return {
            **pred,
            "class": class_name,
            "side": side,
            "part": part,
            "damage_type": damage,
        }

    def calculate_severity(self, pred: Dict[str, Any]) -> str:
        area = pred.get("width", 0) * pred.get("height", 0)
        damage_type = (pred.get("damage_type") or "").lower()
        confidence = pred.get("confidence", 0.0)

        # Explicit high-severity categories
        if damage_type in ["broken", "crash", "shattered"]:
            return "High"

        # Reasonable defaults
        if damage_type == "dent":
            severity = "Medium"
        elif damage_type == "scratch":
            severity = "Low"
        else:
            if area > 20000:
                severity = "High"
            elif area > 5000:
                severity = "Medium"
            else:
                severity = "Low"

        if confidence < 0.6:
            severity = "Low"

        return severity

    def class_to_color(self, severity: str) -> str:
        status = severity.title() if severity else "High"

        if status == "Low":
            return "#22C55E"
        elif status == "Medium":
            return "#F59E0B"
        return "#EF4444"

    async def detect_car_damage(
        self,
        file: UploadFile,
        include_annotated_image: bool = False,
        image_index: int = 0,
    ) -> Dict[str, Any]:
        temp_path = None

        try:
            content = await file.read()
            if not content:
                raise HTTPException(status_code=400, detail="Uploaded image is empty.")

            fd, temp_path = tempfile.mkstemp(suffix=".jpg")
            with os.fdopen(fd, "wb") as f:
                f.write(content)

            result = self.client.run_workflow(
                workspace_name=self.workspace,
                workflow_id=self.workflow_id,
                images={"image": temp_path},
                use_cache=False,
            )

            raw_predictions = self.extract_predictions(result)

            # IMPORTANT:
            # This service processes ONE image at a time.
            # So we assign image_index here and NEVER merge across images.
            for pred in raw_predictions:
                pred["image_index"] = image_index

            nms_predictions = self.apply_nms_per_image(
                raw_predictions,
                image_index=image_index,
            )

            accepted_predictions, review_predictions = self.apply_confidence_filtering(
                nms_predictions
            )

            processed: List[Dict[str, Any]] = []
            for pred in accepted_predictions:
                norm = self.normalize_prediction(pred)
                norm["image_index"] = image_index
                norm["severity"] = self.calculate_severity(norm)
                norm["points"] = 1
                processed.append(norm)

            high_severity_count = len(
                [p for p in processed if (p.get("severity") or "").lower() == "high"]
            )

            response: Dict[str, Any] = {
                "image_index": image_index,
                "predictions": processed,
                "review_predictions": review_predictions,
                "confidence_analysis": self.calculate_weighted_confidence(processed),
                "count": len(processed),
                "high_severity_count": high_severity_count,
                "image_summary": {
                    "image_index": image_index,
                    "count": len(processed),
                    "high_severity_count": high_severity_count,
                    "predictions": processed,
                },
            }

            if include_annotated_image:
                response["annotated_image"] = self.create_image(temp_path, processed)

            return response

        except HTTPException:
            # Intentional errors (e.g. empty image) must not be re-wrapped as 500.
            raise
        except Exception as e:
            logger.error(f"detect_car_damage failed: {str(e)}")
            if _is_connectivity_error(str(e)):
                raise HTTPException(status_code=503, detail=_UNREACHABLE_DETAIL)
            raise HTTPException(status_code=500, detail=str(e))

        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    async def detect_car_damage_from_path(
        self,
        image_path: str,
        image_index: int = 0,
        include_annotated_image: bool = False,
    ) -> Dict[str, Any]:
        try:
            result = self.client.run_workflow(
                workspace_name=self.workspace,
                workflow_id=self.workflow_id,
                images={"image": image_path},
                use_cache=False,
            )

            raw_predictions = self.extract_predictions(result)

            for pred in raw_predictions:
                pred["image_index"] = image_index

            nms_predictions = self.apply_nms_per_image(
                raw_predictions,
                image_index=image_index,
            )

            accepted_predictions, review_predictions = self.apply_confidence_filtering(
                nms_predictions
            )

            processed: List[Dict[str, Any]] = []
            for pred in accepted_predictions:
                norm = self.normalize_prediction(pred)
                norm["image_index"] = image_index
                norm["severity"] = self.calculate_severity(norm)
                norm["points"] = 1
                processed.append(norm)

            high_severity_count = len(
                [p for p in processed if (p.get("severity") or "").lower() == "high"]
            )

            response: Dict[str, Any] = {
                "image_index": image_index,
                "predictions": processed,
                "review_predictions": review_predictions,
                "confidence_analysis": self.calculate_weighted_confidence(processed),
                "count": len(processed),
                "high_severity_count": high_severity_count,
                "image_summary": {
                    "image_index": image_index,
                    "count": len(processed),
                    "high_severity_count": high_severity_count,
                    "predictions": processed,
                },
            }

            if include_annotated_image:
                response["annotated_image"] = self.create_image(image_path, processed)

            return response

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"detect_car_damage_from_path failed: {str(e)}")
            if _is_connectivity_error(str(e)):
                raise HTTPException(status_code=503, detail=_UNREACHABLE_DETAIL)
            raise HTTPException(status_code=500, detail=str(e))

    def create_image_bytes(self, image_path: str, predictions: List[Dict[str, Any]]) -> bytes:
        from PIL import ImageFont

        image = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(image)

        try:
            font = ImageFont.truetype("arial.ttf", 18)
        except Exception:
            font = ImageFont.load_default()

        for pred in predictions:
            x, y = pred["x"], pred["y"]
            w, h = pred["width"], pred["height"]

            x1, y1 = x - w / 2, y - h / 2
            x2, y2 = x + w / 2, y + h / 2

            color = self.class_to_color(pred["severity"])

            draw.rectangle([x1, y1, x2, y2], outline=color, width=2)

            conf_val = int(round(pred.get("confidence", 0) * 100))
            label_text = f"{pred['part']} {pred['damage_type']} {conf_val}%"

            t_left, t_top, t_right, t_bottom = draw.textbbox((0, 0), label_text, font=font)
            text_w = t_right - t_left
            text_h = t_bottom - t_top

            padding = 4
            pill_x1 = x1
            pill_y1 = max(0, y1 - text_h - (padding * 2))
            pill_x2 = x1 + text_w + (padding * 2)
            pill_y2 = y1

            draw.rectangle([pill_x1, pill_y1, pill_x2, pill_y2], fill=color)
            draw.text(
                (pill_x1 + padding, pill_y1 + padding),
                label_text,
                fill="white",
                font=font,
            )

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=90)
        return buffer.getvalue()

    def create_image(self, image_path: str, predictions: List[Dict[str, Any]]) -> str:
        from PIL import ImageFont

        image = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(image)

        try:
            font = ImageFont.truetype("arial.ttf", 18)
        except Exception:
            font = ImageFont.load_default()

        for pred in predictions:
            x, y = pred["x"], pred["y"]
            w, h = pred["width"], pred["height"]

            x1, y1 = x - w / 2, y - h / 2
            x2, y2 = x + w / 2, y + h / 2

            color = self.class_to_color(pred["severity"])

            draw.rectangle([x1, y1, x2, y2], outline=color, width=2)

            conf_val = int(round(pred.get("confidence", 0) * 100))
            label_text = f"{pred['part']} {pred['damage_type']} {conf_val}%"

            t_left, t_top, t_right, t_bottom = draw.textbbox((0, 0), label_text, font=font)
            text_w = t_right - t_left
            text_h = t_bottom - t_top

            padding = 4
            pill_x1 = x1
            pill_y1 = max(0, y1 - text_h - (padding * 2))
            pill_x2 = x1 + text_w + (padding * 2)
            pill_y2 = y1

            draw.rectangle([pill_x1, pill_y1, pill_x2, pill_y2], fill=color)
            draw.text(
                (pill_x1 + padding, pill_y1 + padding),
                label_text,
                fill="white",
                font=font,
            )

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=90)
        return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()

    def extract_predictions(self, workflow_result: Any) -> List[Dict[str, Any]]:
        try:
            if isinstance(workflow_result, list) and len(workflow_result) > 0:
                workflow_result = workflow_result[0]

            if not isinstance(workflow_result, dict):
                return []

            preds: List[Dict[str, Any]] = []

            if isinstance(workflow_result.get("predictions"), list):
                preds = workflow_result["predictions"]

            elif isinstance(workflow_result.get("predictions"), dict):
                inner = workflow_result["predictions"]
                if isinstance(inner.get("predictions"), list):
                    preds = inner["predictions"]

            elif isinstance(workflow_result.get("output"), dict):
                output = workflow_result["output"]
                if isinstance(output.get("predictions"), list):
                    preds = output["predictions"]

            return [p for p in preds if isinstance(p, dict)]

        except Exception as e:
            logger.error(f"Prediction extraction failed: {e}")
            return []

    def apply_nms_per_image(
        self,
        predictions: List[Dict[str, Any]],
        image_index: int,
        iou_threshold: float = 0.5,
    ) -> List[Dict[str, Any]]:
        if not predictions:
            return []

        for pred in predictions:
            pred["image_index"] = image_index

        sorted_predictions = sorted(
            predictions,
            key=lambda x: x.get("confidence", 0),
            reverse=True,
        )

        keep: List[Dict[str, Any]] = []
        suppressed = set()

        for i, pred in enumerate(sorted_predictions):
            if i in suppressed:
                continue

            keep.append(pred)

            for j in range(i + 1, len(sorted_predictions)):
                if j in suppressed:
                    continue

                if pred.get("class") == sorted_predictions[j].get("class"):
                    iou = self.calculate_iou(pred, sorted_predictions[j])
                    if iou >= iou_threshold:
                        suppressed.add(j)

        logger.info(
            f"NMS applied for image_index={image_index}: "
            f"{len(predictions)} -> {len(keep)} predictions"
        )
        return keep

    def apply_confidence_filtering(
        self,
        predictions: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        accepted: List[Dict[str, Any]] = []
        review: List[Dict[str, Any]] = []

        for pred in predictions:
            confidence = pred.get("confidence", 0.0)

            if confidence >= 0.55:
                accepted.append(pred)
            elif confidence >= 0.50:
                pred_copy = pred.copy()
                pred_copy["review_flag"] = True
                review.append(pred_copy)

        logger.info(
            f"Confidence filtering: {len(accepted)} accepted, "
            f"{len(review)} flagged for review, "
            f"{len(predictions) - len(accepted) - len(review)} ignored"
        )
        return accepted, review

    def get_class_weight(self, class_name: str) -> float:
        class_lower = class_name.lower()

        if "bumper" in class_lower:
            return 1.2

        if any(part in class_lower for part in ["bonnet", "boot", "hood", "trunk"]):
            return 1.0

        if any(part in class_lower for part in ["door", "quarter", "panel", "wing", "fender"]):
            return 0.9

        if "roof" in class_lower:
            return 0.8

        if any(part in class_lower for part in ["glass", "light", "headlight", "taillight", "mirror"]):
            return 1.1

        return 1.0

    def calculate_weighted_confidence(self, predictions: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not predictions:
            return {
                "overall_confidence": 0.0,
                "confidence_band": "Low",
                "per_class_confidences": {},
                "weighted_average": 0.0,
                "total_weight": 0.0,
                "class_weights": {},
                "high_severity_count": 0,
            }

        class_groups: Dict[str, List[float]] = {}
        high_severity_count = 0

        for pred in predictions:
            class_name = pred.get("class", "unknown")
            confidence = pred.get("confidence", 0.0)
            severity = pred.get("severity", "").capitalize()

            if severity == "High":
                high_severity_count += 1

            if class_name not in class_groups:
                class_groups[class_name] = []
            class_groups[class_name].append(confidence)

        per_class_confidences: Dict[str, float] = {}
        weighted_sum = 0.0
        total_weight = 0.0

        for class_name, confidences in class_groups.items():
            avg_confidence = sum(confidences) / len(confidences)
            per_class_confidences[class_name] = avg_confidence

            weight = self.get_class_weight(class_name)
            weighted_sum += avg_confidence * weight
            total_weight += weight

        overall_confidence = weighted_sum / total_weight if total_weight > 0 else 0.0

        if overall_confidence >= 0.85:
            confidence_band = "High"
        elif overall_confidence >= 0.70:
            confidence_band = "Medium"
        else:
            confidence_band = "Low"

        return {
            "overall_confidence": overall_confidence,
            "confidence_band": confidence_band,
            "per_class_confidences": per_class_confidences,
            "weighted_average": overall_confidence,
            "total_weight": total_weight,
            "class_weights": {
                class_name: self.get_class_weight(class_name)
                for class_name in class_groups.keys()
            },
            "high_severity_count": high_severity_count,
        }

    def calculate_iou(self, box1: Dict[str, Any], box2: Dict[str, Any]) -> float:
        x1_1 = box1["x"] - box1["width"] / 2
        y1_1 = box1["y"] - box1["height"] / 2
        x2_1 = box1["x"] + box1["width"] / 2
        y2_1 = box1["y"] + box1["height"] / 2

        x1_2 = box2["x"] - box2["width"] / 2
        y1_2 = box2["y"] - box2["height"] / 2
        x2_2 = box2["x"] + box2["width"] / 2
        y2_2 = box2["y"] + box2["height"] / 2

        x1_i = max(x1_1, x1_2)
        y1_i = max(y1_1, y1_2)
        x2_i = min(x2_1, x2_2)
        y2_i = min(y2_1, y2_2)

        if x2_i <= x1_i or y2_i <= y1_i:
            return 0.0

        intersection = (x2_i - x1_i) * (y2_i - y1_i)
        union = box1["width"] * box1["height"] + box2["width"] * box2["height"] - intersection

        return intersection / union if union > 0 else 0.0


roboflow_service = RoboflowService()