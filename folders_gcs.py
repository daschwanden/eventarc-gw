# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Any

from openrelik_api_client.api_client import APIClient


class FoldersAPI:

    def __init__(self, api_client: APIClient):
        super().__init__()
        self.api_client = api_client

    def create_root_folder(self, display_name: str) -> int | None:
        """Create a root folder.

        Args:
            display_name (str): Folder display name.

        Returns:
            int: Folder ID for the new root folder, or None otherwise.

        Raises:
            HTTPError: If the API request failed.
        """
        folder_id = None
        endpoint = f"{self.api_client.base_url}/folders/"
        params = {"display_name": display_name}
        response = self.api_client.session.post(endpoint, json=params)
        response.raise_for_status()
        if response.status_code == 201:
            folder_id = response.json().get("id")
        return folder_id

    def create_subfolder(self, folder_id: int, display_name: str) -> int | None:
        """Create a subfolder within the given folder ID.

        Args:
            folder_id: The ID of the parent folder.
            display_name: The name of the subfolder to check.

        Returns:
            int: Folder ID for the new root folder, or None.

        Raises:
            HTTPError: If the API request failed.
        """
        endpoint = f"{self.api_client.base_url}/folders/{folder_id}/folders"
        folder_id = None
        data = {"display_name": display_name}
        response = self.api_client.session.post(endpoint, json=data)
        response.raise_for_status()
        if response.status_code == 201:
            folder_id = response.json().get("id")
        return folder_id

    def folder_exists(self, folder_id: int) -> bool:
        """Checks if a folder with the given ID exists.

        Args:
            folder_id: The ID of the folder to check.

        Returns:
            True if the folder exists, False otherwise.

        Raises:
            HTTPError: If the API request failed.
        """
        endpoint = f"{self.api_client.base_url}/folders/{folder_id}"
        response = self.api_client.session.get(endpoint)
        response.raise_for_status()
        return response.status_code == 200

    def update_folder(
        self, folder_id: int, folder_data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Updates an existing folder.

        Args:
            folder_id: The ID of the folder to update.
            folder_data: The updated folder data.

        Returns:
            The updated folder data, or None.

        Raises:
            HTTPError: If the API request failed.
        """
        endpoint = f"{self.api_client.base_url}/folders/{folder_id}"
        response = self.api_client.session.patch(endpoint, json=folder_data)
        response.raise_for_status()
        return response.json()

    def delete_folder(
        self, folder_id: int) -> bool:
        """Deletes an existing folder.

        Args:
            folder_id: The ID of the folder to update.

        Returns:
            True if the request was successful.

        Raises:
            HTTPError: If the API request failed.
        """
        endpoint = f"{self.api_client.base_url}/folders/{folder_id}"
        response = self.api_client.session.delete(endpoint)
        response.raise_for_status()
        return response.status_code == 204
