# Copyright 2025 Google, LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# [START eventarc_http_endpoint]
#!/usr/bin/env python3
from google.cloud import storage
from http.server import BaseHTTPRequestHandler, HTTPServer
from openrelik_api_client.api_client import APIClient
from openrelik_api_client.workflows import WorkflowsAPI
from typing import Any
from api_client_gcs import APIClientGCS
from folders_gcs import FoldersAPI

import json
import logging
import os

class S(BaseHTTPRequestHandler):
    def _set_response(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

    def do_GET(self):
        logging.info("GET request,\nPath: %s\nHeaders:\n%s\n", str(self.path), str(self.headers))
        self._set_response()
        self.wfile.write("GET request for {}".format(self.path).encode('utf-8'))

    def do_POST(self):
        """Handles POST requests."""
        content_length = int(self.headers.get('Content-Length', 0))
        post_data_bytes = self.rfile.read(content_length)

        # For robust JSON handling, you might check the Content-Type header
        content_type = self.headers.get('Content-Type', '')
        is_json_request = 'application/json' in content_type.lower()

        if not is_json_request:
            print("Warning: Received POST request without 'application/json' Content-Type.")
            # You might choose to reject non-JSON requests here if strictly required
            # For this example, we'll still try to process it as JSON in process_post_data

        parsed_data, status_message = self.process_post_data(post_data_bytes)

        if parsed_data is not None:
            self.send_response(200)
            response_content_type = 'application/json' # Respond with JSON if successfully parsed
            response_payload = json.dumps({
                "status": "success",
                "received_data": parsed_data,
                "message": status_message
            })
            logging.info(response_payload)
            self.process_payload_gcs(response_payload)
        else:
            # Handle cases where parsing failed
            if "Invalid JSON" in status_message:
                self.send_response(400) # Bad Request
            elif "decode" in status_message.lower(): # Unicode decode error
                self.send_response(400) # Bad Request
            else:
                self.send_response(500) # Internal Server Error
            response_content_type = 'application/json' # Still good to respond with JSON for errors
            response_payload = json.dumps({
                "status": "error",
                "message": status_message
            })

        self.send_header('Content-type', response_content_type)
        self.end_headers()
        self.wfile.write(response_payload.encode('utf-8'))

    def get_folder_id(self, api_client, folder_id, object_path):
       folders_client = FoldersAPI(api_client)
       i = 0
       while i < len(object_path)-1:
           folder = object_path[i]
           logging.info(f"Processing {folder}, folder_id {folder_id}")
           if not folder_id:
               # No folder_id means that we start building the folder structure from the root
               response = api_client.get("/folders/")
           else:
               response = api_client.get(f"/folders/{folder_id}/folders")
           exists = False
           logging.info(f"Folders response {response}, folder_id {folder_id}")
           for subfolder in response.json():
               if subfolder.get("display_name") == folder:
                   exists = True
                   folder_id = subfolder.get("id")
                   break
           if not exists:
              try:
                  folder_id = folders_client.create_subfolder(folder_id, folder)
              except Exception as e:
                  logging.info(f"Error creating folder {folder} : {e}")
           i += 1

       return folder_id   


    def process_payload_gcs(self, payload_string):
        """
        Processes the payload data
        1) Stream from GCS to OpenRelik
        2) Kick off OpenRelik Workflow
        """
        payload = json.loads(payload_string)
        received_data = payload.get("received_data")
        if received_data:
            bucket_name = received_data.get("bucket")
            object_name = received_data.get("name")
            size = int(received_data.get("size"))
            if bucket_name and object_name:
                logging.info(f"Bucket: {bucket_name} , Object: {object_name}, Size: {size}")
                try:
                    storage_client = storage.Client()
                    bucket = storage_client.bucket(bucket_name)
                    bucket_info = storage_client.get_bucket(bucket_name)
                    bucket_labels = bucket_info.labels
                    logging.info(f"Bucket labels: {bucket_labels}")
                    template_id = int(bucket_labels.get('template_id'))
                    folder_id = int(bucket_labels.get('folder_id'))
                    logging.info(f"folder_id: {folder_id} , template_id: {template_id}")

                    try:
                        # Create the API client. It will handle token refreshes automatically.
                        api_server_url = "http://my-release-openrelik-api:8710"
                        # Get the OpenRelik API key from environment variable
                        api_key = os.getenv("OPENRELIK_API_KEY")
                        api_client = APIClientGCS(api_server_url, api_key)
                        
                        object_path = object_name.split('/')
                        if len(object_path) > 1:
                            file_name = object_path[-1]
                            folder_id = self.get_folder_id(api_client, folder_id, object_path)
                            logging.info(f"folder_id updated to: {folder_id}")
                        else:
                            file_name = object_name

                        logging.info(f"File name: {file_name}")
         
                        # 1) Stream blob from GCS to OpenRelik
                        uploaded_file_id = api_client.upload_file_from_gcs(bucket_name, object_name, file_name, size, folder_id)
                        if uploaded_file_id:
                            logging.info(f"Successfully streamed {file_name} to OpenRelik, file_id: {uploaded_file_id}")
                            file_ids = [uploaded_file_id]
                            # 2) Kick off OpenRelik Workflow
                            workflows = WorkflowsAPI(api_client)
                            workflow_id = workflows.create_workflow(folder_id, file_ids, template_id)
                            if workflow_id:
                                logging.info(f"Successfully created workflow, workflow_id: {workflow_id}")
                                workflow = workflows.run_workflow(folder_id, workflow_id)
                                if workflow:
                                    logging.info(f"Successfully ran workflow, workflow_id: {workflow_id}")
                                else:
                                    logging.info(f"Error running workflow, workflow_id: {workflow_id}")
                            else:
                                logging.info(f"Error creating workflow, workflow_id: {workflow_id}")
                        else:
                            logging.info(f"Error uploading {object_name} to OpenRelik")
                    except Exception as oe:
                        logging.info(f"Error uploading {object_name} from GCS to OpenRelik: {oe}")

                except Exception as ge:
                    logging.info(f"Error streaming {object_name} from bucket {bucket_name}: {ge}")
            else:
                logging.info("Failed to parse payload")

    def process_post_data(self, data_bytes):
        """
        Processes the raw bytes of the POST data, assuming it's JSON.
        Returns a tuple: (parsed_json_object, status_message)
        parsed_json_object will be None if parsing fails.
        """
        try:
            # 1. Decode the bytes to a string (UTF-8 is common for JSON)
            data_string = data_bytes.decode('utf-8')
            print(f"Received raw string data: {data_string}")
        except UnicodeDecodeError:
            error_msg = "Error: Could not decode POST data from bytes (expected UTF-8)."
            print(error_msg)
            return None, error_msg

        try:
            # 2. Parse the string into a Python dictionary (or list if it's a JSON array)
            parsed_json = json.loads(data_string)
            print(f"Successfully parsed JSON: {parsed_json}")
            
            # You can now work with parsed_json as a Python dict/list
            # Example: Accessing a value if it's a dictionary
            # if isinstance(parsed_json, dict) and 'name' in parsed_json:
            #     print(f"Name from JSON: {parsed_json['name']}")

            return parsed_json, "JSON data processed successfully."
        except json.JSONDecodeError as e:
            error_msg = f"Error: Invalid JSON format in POST data. Details: {e}"
            print(error_msg)
            return None, error_msg
        except Exception as e:
            # Catch any other unexpected errors during processing
            error_msg = f"An unexpected error occurred during JSON processing: {e}"
            print(error_msg)
            return None, error_msg

def run(server_class=HTTPServer, handler_class=S, port=8080):
    logging.basicConfig(level=logging.INFO)
    server_address = ('', port)
    http_server = server_class(server_address, handler_class)
    logging.info('Starting eventarc-gw HTTP Server at port %d...\n', port)
    try:
        http_server.serve_forever()
    except KeyboardInterrupt:
        pass
    http_server.server_close()
    logging.info('Stopping eventarc-gw HTTP Server...\n')

if __name__ == '__main__':
    from sys import argv

    if len(argv) == 2:
        run(port=int(argv[1]))
    else:
        run()
# [END eventarc_http_endpoint]
