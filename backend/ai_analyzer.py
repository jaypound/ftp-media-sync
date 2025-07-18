import os
import json
import logging
from typing import Dict, List, Any
import openai
from anthropic import Anthropic
import math

logger = logging.getLogger(__name__)

class AIAnalyzer:
    def __init__(self, api_provider="openai", api_key=None, model=None, auto_setup=True):
        self.api_provider = api_provider.lower()
        self.api_key = api_key
        self.model = model
        self.client = None
        
        # Default models
        if not self.model:
            if self.api_provider == "openai":
                self.model = "gpt-3.5-turbo"
            elif self.api_provider == "anthropic":
                self.model = "claude-3-sonnet-20240229"
        
        if auto_setup:
            self.setup_client()
    
    def setup_client(self):
        """Setup API client"""
        try:
            logger.info(f"Setting up AI client: provider={self.api_provider}, model={self.model}")
            logger.debug(f"API key present: {bool(self.api_key)}")
            
            if self.api_provider == "openai":
                # For OpenAI client initialization (v1.97.0+)
                try:
                    if self.api_key:
                        self.client = openai.OpenAI(api_key=self.api_key)
                    else:
                        self.client = openai.OpenAI()
                    logger.info(f"OpenAI client setup successful with model: {self.model}")
                except Exception as openai_error:
                    logger.error(f"OpenAI client setup failed: {openai_error}")
                    self.client = None
                
            elif self.api_provider == "anthropic":
                try:
                    if self.api_key:
                        self.client = Anthropic(api_key=self.api_key)
                    else:
                        self.client = Anthropic()
                    logger.info(f"Anthropic client setup successful with model: {self.model}")
                except Exception as anthropic_error:
                    logger.error(f"Anthropic client setup failed: {anthropic_error}")
                    self.client = None
                
        except Exception as e:
            logger.error(f"Error setting up AI client: {str(e)}")
            logger.error(f"Provider: {self.api_provider}, API key present: {bool(self.api_key)}")
            self.client = None
    
    def create_analysis_prompt(self, transcript: str) -> str:
        """Create the analysis prompt for the AI"""
        return f"""
Analyze the following video transcript and provide a detailed analysis in JSON format. 
The analysis should include:

1. summary: A comprehensive summary of the content (2-3 sentences)
2. topics: List of main topics discussed (array of strings)
3. locations: List of any locations mentioned (array of strings)
4. people: List of any people mentioned (array of strings)
5. events: List of any events discussed (array of strings)
6. engagement_score: Score from 0-100 indicating how engaging this content would be for viewers
7. engagement_score_reasons: Text explanation of the engagement score
8. shelf_life_score: One of "short", "medium", or "long" indicating content longevity
9. shelf_life_reasons: Text explanation of the shelf life assessment

Please provide only valid JSON in your response, no additional text.

Transcript:
{transcript}
"""
    
    def chunk_text(self, text: str, max_chars: int = 4000) -> List[str]:
        """Split text into chunks for processing"""
        if len(text) <= max_chars:
            return [text]
        
        chunks = []
        words = text.split()
        current_chunk = []
        current_length = 0
        
        for word in words:
            word_length = len(word) + 1  # +1 for space
            if current_length + word_length > max_chars and current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = [word]
                current_length = word_length
            else:
                current_chunk.append(word)
                current_length += word_length
        
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        
        return chunks
    
    def analyze_chunk_openai(self, chunk: str) -> Dict[str, Any]:
        """Analyze a text chunk using OpenAI"""
        try:
            prompt = self.create_analysis_prompt(chunk)
            logger.debug(f"Sending prompt to OpenAI (length: {len(prompt)} chars)")
            
            # Use the modern OpenAI client (v1.97.0+)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert content analyst. Provide detailed analysis in valid JSON format only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            content = response.choices[0].message.content.strip()
            
            logger.info(f"OpenAI response received (length: {len(content)} chars)")
            logger.debug(f"OpenAI response: {content}")
            
            # Try to parse JSON response
            try:
                result = json.loads(content)
                logger.info(f"Successfully parsed OpenAI JSON response")
                return result
            except json.JSONDecodeError:
                logger.warning("AI response was not valid JSON, attempting to extract JSON")
                logger.debug(f"Raw response: {content}")
                # Try to extract JSON from response
                start = content.find('{')
                end = content.rfind('}') + 1
                if start != -1 and end != -1:
                    json_str = content[start:end]
                    result = json.loads(json_str)
                    logger.info(f"Successfully extracted JSON from OpenAI response")
                    return result
                else:
                    raise ValueError("No valid JSON found in response")
                    
        except Exception as e:
            logger.error(f"Error analyzing chunk with OpenAI: {str(e)}")
            return None
    
    def analyze_chunk_anthropic(self, chunk: str) -> Dict[str, Any]:
        """Analyze a text chunk using Anthropic"""
        try:
            prompt = self.create_analysis_prompt(chunk)
            logger.debug(f"Sending prompt to Anthropic (length: {len(prompt)} chars)")
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                temperature=0.3,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            content = response.content[0].text.strip()
            logger.info(f"Anthropic response received (length: {len(content)} chars)")
            logger.debug(f"Anthropic response: {content}")
            
            # Try to parse JSON response
            try:
                result = json.loads(content)
                logger.info(f"Successfully parsed Anthropic JSON response")
                return result
            except json.JSONDecodeError:
                logger.warning("AI response was not valid JSON, attempting to extract JSON")
                logger.debug(f"Raw response: {content}")
                # Try to extract JSON from response
                start = content.find('{')
                end = content.rfind('}') + 1
                if start != -1 and end != -1:
                    json_str = content[start:end]
                    result = json.loads(json_str)
                    logger.info(f"Successfully extracted JSON from Anthropic response")
                    return result
                else:
                    raise ValueError("No valid JSON found in response")
                    
        except Exception as e:
            logger.error(f"Error analyzing chunk with Anthropic: {str(e)}")
            return None
    
    def analyze_chunk(self, chunk: str) -> Dict[str, Any]:
        """Analyze a text chunk using the configured AI provider"""
        if self.api_provider == "openai":
            return self.analyze_chunk_openai(chunk)
        elif self.api_provider == "anthropic":
            return self.analyze_chunk_anthropic(chunk)
        else:
            logger.error(f"Unsupported AI provider: {self.api_provider}")
            return None
    
    def merge_analyses(self, chunk_analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge multiple chunk analyses into a single result"""
        if not chunk_analyses:
            return None
        
        if len(chunk_analyses) == 1:
            return chunk_analyses[0]
        
        # Initialize merged result
        merged = {
            "summary": "",
            "topics": [],
            "locations": [],
            "people": [],
            "events": [],
            "engagement_score": 0,
            "engagement_score_reasons": "",
            "shelf_life_score": "medium",
            "shelf_life_reasons": ""
        }
        
        # Merge arrays (deduplicate)
        all_topics = set()
        all_locations = set()
        all_people = set()
        all_events = set()
        
        summaries = []
        engagement_scores = []
        engagement_reasons = []
        shelf_life_scores = []
        shelf_life_reasons = []
        
        for analysis in chunk_analyses:
            if analysis:
                summaries.append(analysis.get("summary", ""))
                engagement_scores.append(analysis.get("engagement_score", 0))
                engagement_reasons.append(analysis.get("engagement_score_reasons", ""))
                shelf_life_scores.append(analysis.get("shelf_life_score", "medium"))
                shelf_life_reasons.append(analysis.get("shelf_life_reasons", ""))
                
                all_topics.update(analysis.get("topics", []))
                all_locations.update(analysis.get("locations", []))
                all_people.update(analysis.get("people", []))
                all_events.update(analysis.get("events", []))
        
        # Merge results
        merged["summary"] = " ".join(summaries)
        merged["topics"] = list(all_topics)
        merged["locations"] = list(all_locations)
        merged["people"] = list(all_people)
        merged["events"] = list(all_events)
        
        # Average engagement score
        if engagement_scores:
            merged["engagement_score"] = round(sum(engagement_scores) / len(engagement_scores))
        
        # Combine reasons
        merged["engagement_score_reasons"] = " ".join(engagement_reasons)
        merged["shelf_life_reasons"] = " ".join(shelf_life_reasons)
        
        # Most common shelf life score
        if shelf_life_scores:
            merged["shelf_life_score"] = max(set(shelf_life_scores), key=shelf_life_scores.count)
        
        return merged
    
    def analyze_transcript(self, transcript: str, max_chunk_size: int = 4000) -> Dict[str, Any]:
        """Analyze a transcript, handling chunking if necessary"""
        try:
            if not self.client:
                logger.error("AI client not initialized")
                return None
            
            logger.info(f"Analyzing transcript of {len(transcript)} characters")
            
            # Split into chunks if necessary
            chunks = self.chunk_text(transcript, max_chunk_size)
            logger.info(f"Split transcript into {len(chunks)} chunks")
            
            # Analyze each chunk
            chunk_analyses = []
            for i, chunk in enumerate(chunks):
                logger.info(f"Analyzing chunk {i+1}/{len(chunks)}")
                analysis = self.analyze_chunk(chunk)
                if analysis:
                    chunk_analyses.append(analysis)
                else:
                    logger.warning(f"Failed to analyze chunk {i+1}")
            
            # Merge chunk analyses
            if chunk_analyses:
                merged_analysis = self.merge_analyses(chunk_analyses)
                logger.info("Successfully completed transcript analysis")
                return merged_analysis
            else:
                logger.error("No chunks were successfully analyzed")
                return None
                
        except Exception as e:
            logger.error(f"Error analyzing transcript: {str(e)}")
            return None

# Global AI analyzer instance
ai_analyzer = AIAnalyzer(auto_setup=False)