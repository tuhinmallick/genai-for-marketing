# Copyright 2023 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""
Utility module to:
 - Resize image bytes
 - Generate an image with Imagen
 - Edit an image with Imagen
 - Render the image generation and editing UI
"""

import base64
import io
import math
import utils_edit_image

from google.cloud import aiplatform
from google.protobuf import json_format
from google.protobuf.struct_pb2 import Value
from PIL import Image
import streamlit as st
from typing import List

from utils_config import GLOBAL_CFG, PAGES_CFG, MODEL_CFG


# Set project parameters
PROJECT_ID = GLOBAL_CFG["project_id"]
LOCATION = GLOBAL_CFG["location"]

# Set project parameters
IMAGE_MODEL_NAME = MODEL_CFG["image"]["image_model_name"]
IMAGEN_API_ENDPOINT = f'{LOCATION}-aiplatform.googleapis.com'
IMAGEN_ENDPOINT = f'projects/{PROJECT_ID}/locations/{LOCATION}/publishers/google/models/{IMAGE_MODEL_NAME}'
IMAGE_UPLOAD_BYTES_LIMIT = PAGES_CFG["16_image_generation"][
                                     "image_upload_bytes_limit"]
# The AI Platform services require regional API endpoints.
client_options = {"api_endpoint": IMAGEN_API_ENDPOINT}
# Initialize client that will be used to create and send requests.
imagen_client = aiplatform.gapic.PredictionServiceClient(
    client_options=client_options
)


def resize_image_bytes(
        bytes_data: bytes, 
        bytes_limit: int=IMAGE_UPLOAD_BYTES_LIMIT) -> bytes:
    """Resizes an image to a specified byte limit.

    Args:
        bytes_data: 
            The image data in bytes. (bytes)
        bytes_limit: 
            The maximum byte size of the resized image. (int)

    Returns:
        The resized image data in bytes.

    Raises:
        Image.ImageTooBigError: If the image is larger than the bytes_limit.
    """
    with io.BytesIO(bytes_data) as buffer_in:
        img_to_resize = Image.open(buffer_in)
        width = img_to_resize.size[0]
        aspect = img_to_resize.size[0] / img_to_resize.size[1]
        bytes_size = len(bytes_data)

        while bytes_size > bytes_limit :    
            resize_factor = bytes_size / (bytes_limit*0.9)
            width = width / math.sqrt(resize_factor)  
            height = width / aspect
            # resize from img_orig to not lose quality
            img = img_to_resize.resize((int(width), int(height)))
            
            with io.BytesIO() as buffer_out:
                img.save(buffer_out, format="PNG")
                bytes_data = buffer_out.getvalue()
                bytes_size = len(bytes_data)
    
    return bytes_data


def predict_image(
    instance_dict: dict,
    parameters: dict
):
    """Predicts the output of imagen on a given instance dict.

    Args:
        instance_dict: 
            The input to the large language model. (dict)
        parameters: 
            The parameters for the prediction. (dict)

    Returns:
        A list of strings containing the predictions.

    Raises:
        aiplatform.exceptions.NotFoundError: If the endpoint does not exist.
        aiplatform.exceptions.BadRequestError: If the input is invalid.
        aiplatform.exceptions.InternalServerError: If an internal error occurred.
    """

    instance = json_format.ParseDict(instance_dict, Value())
    instances = [instance]
    parameters_client = json_format.ParseDict(parameters, Value())
    response = imagen_client.predict(
        endpoint=IMAGEN_ENDPOINT,
        instances=instances,
        parameters=parameters_client
    )
    
    return response.predictions


def image_generation(
        prompt:str,
        sample_count:int,
        sample_image_size: int,
        aspect_ratio: str,
        state_key: str):
    """Generates an image from a prompt.

    Args:
        prompt: 
            The prompt to use to generate the image.
        sample_count: 
            The number of images to generate.
        sample_image_size: 
            The size of the generated images.
        aspect_ratio: 
            The aspect ratio of the generated images.
        state_key: 
            The key to use to store the generated images in the session state.

    Returns:
        None.
    """

    st.session_state[state_key] = predict_image(
        instance_dict={
            "prompt": prompt
        },
        parameters={
            'sampleCount':sample_count,
            'sampleImageSize':sample_image_size,
            'aspectRatio':aspect_ratio
        }
    )


def edit_image_generation(
        prompt:str,
        sample_count:int,
        bytes_data:bytes,
        state_key: str,
        mask_bytes_data: bytes=b""):
    """Generates an edited image from a prompt and a base image.

    Args:
        prompt: 
            A string that describes the desired edit to the image.
        sample_count: 
            The number of edited images to generate.
        bytes_data: 
            The image data in bytes.
        state_key: 
            The key to store the generated images in the session state.
        mask_bytes_data: 
            The mask data in bytes.

    Returns:
        None.
    """
    input_dict = {
        'prompt': prompt,
        'image': {
            'bytesBase64Encoded': base64.b64encode(bytes_data).decode('utf-8')
        }
    }
    
    if mask_bytes_data:
        input_dict["mask"] = {
            "image": {
                "bytesBase64Encoded": base64.b64encode(
            mask_bytes_data).decode('utf-8')
            }
        }
    
    st.session_state[state_key] = predict_image(
        instance_dict=input_dict,
        parameters={
            'sampleCount':sample_count
        }
    )


def render_one_image(
        images_key: str,
        image_position: int,
        select_button: bool=False,
        selected_image_key: str="",
        edit_button: bool=False,
        image_to_edit_key: str="",
        download_button: bool=True):
    """
    Renders one image from a list of images.

    Args:
        images_key: 
            The key in the session state that stores the list of images.
        image_position: 
            The index of the image to render.
        select_button: 
            Whether to show a button that allows the user to select the image.
        selected_image_key: 
            The key in the session state to store the selected image.
        edit_button: 
            Whether to show a button that allows the user to edit the image.
        image_to_edit_key: 
            The key in the session state to store the edited image.
        download_button: 
            Whether to show a button that allows the user to download the image.

    Returns:
        None.
    """
    image = io.BytesIO(
        base64.b64decode(
        st.session_state[images_key][image_position]["bytesBase64Encoded"])
    )
    st.image(image)

    if download_button:
        st.download_button(
            label='Download',
            key=f"_btn_download_{images_key}_{image_position}",
            data=image,
            file_name='image.png',
        )

    if select_button and selected_image_key:
        if st.button(
            "Select", key=f"_btn_select_{images_key}_{image_position}"):
            st.session_state[selected_image_key] = image

    if st.button("Edit", key=f"_btn_edit_{images_key}_{image_position}"):
        if edit_button and image_to_edit_key:
            st.session_state[image_to_edit_key] = image.getvalue()


def generate_image_columns(
        images_key: str,
        select_button: bool=False,
        selected_image_key: str="",
        edit_button: bool=True,
        image_to_edit_key: str="",
        download_button: bool=True):
    """Generates a grid of image columns.

    Args:
        images_key (str): 
            The key in the session state that stores the images.
        select_button (bool, optional): 
            Whether to show a button to select the image. Defaults to False.
        selected_image_key (str, optional): 
            The key in the session state that stores the selected image. Defaults to an empty string.
        edit_button (bool, optional): 
            Whether to show a button to edit the image. Defaults to False.
        image_to_edit_key (str, optional): 
            The key in the session state that stores the image to edit. Defaults to an empty string.
        download_button (bool, optional): 
            Whether to show a button to download the image. Defaults to True.

    Returns:
        None.
    """
    image_count = len(st.session_state[images_key])
    counter = 0
    while image_count > 0:
        cols = st.columns([25,25,25,25])
        for i, col in enumerate(cols):
            with col:
                try:
                    render_one_image(
                        images_key,
                        i+counter,
                        select_button,
                        selected_image_key,
                        edit_button,
                        image_to_edit_key,
                        download_button)
                except:
                    continue
        counter+=4
        image_count-=4


def render_image_generation_ui(
        image_text_prompt_key: str,
        generated_images_key: str,
        pre_populated_prompts: List[str] = ["an image of a cat"],
        select_button: bool=False,
        selected_image_key: str='',
        edit_button: bool=False,
        title: str="Generate Images",
        image_to_edit_key: str='',
        download_button: bool=True, 
        auto_submit_first_pre_populated: bool=False):
    """Renders a user interface for generating images.

    Args:
        image_text_prompt_key: 
            The key used to store the user's text prompt in the session state.
        generated_images_key: 
            The key used to store the generated images in the session state.
        pre_populated_prompts: 
            A list of pre-populated prompts.
        select_button: 
            Whether to show a button to select a pre-populated prompt.
        selected_image_key: 
            The key used to store the selected image in the session state.
        edit_button: 
            Whether to show a button to edit the selected image.
        title: 
            The title of the user interface.
        image_to_edit_key: 
            The key used to store the image to edit in the session state.
        download_button: 
            Whether to show a button to download the generated images.
        auto_submit_first_pre_populated: 
            Whether to automatically submit the form with the first pre-populated prompt.

    Returns:
        None.
    """

    SAMPLE_COUNT = [8, 4, 2, 1]
    SAMPLE_IMAGE_SIZE = [256, 64, 512, 1024]
    ASPECT_RATIO = ['1:1', '5:4', '3:2', '7:4', '4:3', '16:9', '9:16']

    def submitted():
        st.session_state[image_text_prompt_key] = st.session_state[
            f"{image_text_prompt_key}_text_area"]

    if image_text_prompt_key in st.session_state:
        st.session_state[
            f"{image_text_prompt_key}_text_area"] = st.session_state[
                image_text_prompt_key]

    with st.form('image_form'):
        st.write(f"**{title}**")

        select_prompt = st.selectbox(
            'Select one of the pre populated prompts', pre_populated_prompts
        )

        expanded = (
            f"{image_text_prompt_key}_text_area" in st.session_state
            and st.session_state[f"{image_text_prompt_key}_text_area"] != ''
        )
        with st.expander('[Optional] Write a custom prompt', expanded=expanded):
            st.write('''Provide a custom prompt to generate images. 
                If you provide a custom prompt, the selected option from 
                the dropdown menu will not be considered.''')
            image_custom_prompt = st.text_area(
                'Generate a custom prompt using natural language',
                key=f"{image_text_prompt_key}_text_area")

        st.write('**Model parameters**')
        col1, col2, col3 = st.columns([1,1,1])

        with col1:
            sample_count = st.selectbox('Number of samples', SAMPLE_COUNT)
        with col2:
            sample_image_size = st.selectbox('Sample Image Size', SAMPLE_IMAGE_SIZE)
        with col3:
            aspect_ratio = st.selectbox('Aspect Ratio', ASPECT_RATIO) 

        # Every form must have a submit button.
        submit_prompt = st.form_submit_button("Submit", on_click=submitted)

    if submit_prompt:
        if image_custom_prompt != '':
            st.session_state[image_text_prompt_key] = image_custom_prompt
            question = image_custom_prompt
        else:
            question = select_prompt

        try:
            with st.spinner('Generating images ...'):
                image_generation(
                    question or "",
                    sample_count or 1,
                    sample_image_size or 256,
                    aspect_ratio or "1:1",
                    generated_images_key)
        except:
            st.error('Could not generate image. Try a different prompt.')

    if auto_submit_first_pre_populated:
        if generated_images_key not in st.session_state:
            with st.spinner('Generating images ...'):
                image_generation(
                    pre_populated_prompts[0],
                    SAMPLE_COUNT[0],
                    SAMPLE_IMAGE_SIZE[0],
                    ASPECT_RATIO[0],
                    generated_images_key)

    if generated_images_key in st.session_state:
        generate_image_columns(
            generated_images_key,
            select_button,
            selected_image_key,
            edit_button,
            image_to_edit_key,
            download_button)


def render_image_edit_prompt(
        edit_image_prompt_key: str,
        edited_images_key: str,
        upload_file: bool=True,
        image_to_edit_key: str="",
        mask_image: bool=False,
        mask_image_key: str="",
        select_button: bool=False,
        selected_image_key: str="",
        download_button: bool=True,
        file_uploader_key: str=""):
    """
    Renders a prompt for editing an image.

    Args:
        edit_image_prompt_key: 
            The key to store the edit image prompt in the session state.
        edited_images_key: 
            The key to store the edited images in the session state.
        upload_file: 
            Whether to allow users to upload an image to edit.
        image_to_edit_key: 
            The key to store the image to edit in the session state.
        mask_image: 
            Whether to allow users to mask the image to edit.
        mask_image_key: 
            The key to store the mask image in the session state.
        select_button: 
            Whether to show a button to select an image to edit.
        selected_image_key: 
            The key to store the selected image in the session state.
        download_button: 
            Whether to show a button to download the edited images.
        file_uploader_key: 
            The key to store the file uploader in the session state.

    Returns:
        None.
    """

    SAMPLE_COUNT = [8, 4, 2, 1]

    def submitted():
        st.session_state[edit_image_prompt_key] = st.session_state[
            f"{edit_image_prompt_key}_text_area"]
    
    if edit_image_prompt_key in st.session_state:
        st.session_state[
            f"{edit_image_prompt_key}_text_area"] = st.session_state[
                edit_image_prompt_key]
    
    if upload_file:
        with st.form(f"{file_uploader_key}_form", clear_on_submit=True):
            uploaded_file = st.file_uploader(
                'Upload your image here. It MUST be in PNG or JPEG format.',
                type=['png', 'jpg'],
                key=file_uploader_key)
            submit_button_uploader = st.form_submit_button('Upload Image')
        if submit_button_uploader:
            if uploaded_file is not None:
                st.session_state[image_to_edit_key] = uploaded_file.getvalue()
                if mask_image and mask_image_key in st.session_state:
                    del st.session_state[mask_image_key]
    
    if image_to_edit_key in st.session_state:
        if image_to_edit_key in st.session_state and mask_image:
            with st.expander(
                "**[Optional] Paint where to edit in the image**", expanded=True):
                utils_edit_image.edit_image_canvas(
                        mask_image_key,
                        resize_image_bytes(st.session_state[image_to_edit_key]))
        else:
            st.image(st.session_state[image_to_edit_key])

        with st.form(f'{edited_images_key}_edit_image'):
            st.write('**Generate edited images**')

            edit_image_prompt = st.text_area(
                'Generate a prompt using natural language to edit the image',
                key=f"{edit_image_prompt_key}_text_area")

            st.write('**Model parameters**')
            col1, _, _ = st.columns([1,1,1])

            with col1:
                sample_count = st.selectbox('Number of samples', SAMPLE_COUNT)

            submit_button = st.form_submit_button('Edit Image', on_click=submitted)

        if submit_button:
            bytes_data = st.session_state[image_to_edit_key]
            
            if bytes_data:
                if len(bytes_data) > IMAGE_UPLOAD_BYTES_LIMIT:
                    bytes_data = resize_image_bytes(bytes_data)
                
                if not edit_image_prompt:
                    st.error("Provide a prompt for editing the image")
                else:
                    st.session_state[edit_image_prompt_key] = edit_image_prompt
                    try:
                        with st.spinner('Generating Edited images ...'):
                            edit_image_generation(
                                st.session_state[edit_image_prompt_key],
                                sample_count or 1,
                                bytes_data,
                                edited_images_key,
                                st.session_state.get(mask_image_key, b"") if mask_image and mask_image_key else b"")
                    except Exception as e:
                        st.error(e)
                        st.error('Could not edit image. Try a different prompt.')
            else:
                st.error("No image found to edit")

    if edited_images_key in st.session_state:
        generate_image_columns(
            edited_images_key,
            select_button,
            selected_image_key,
            download_button=download_button)


def render_image_generation_and_edition_ui(
        image_text_prompt_key: str,
        generated_images_key: str,
        edit_image_prompt_key: str,
        pre_populated_prompts: List[str]=["an image of a cat"],
        select_button: bool=False,
        selected_image_key: str="",
        edit_button: bool=False,
        title: str="Generate Images",
        image_to_edit_key: str="",
        edit_with_mask: bool=False,
        mask_image_key: str="",
        edited_images_key: str="",
        download_button: bool=False,
        auto_submit_first_pre_populated=False):
    
    render_image_generation_ui(
        image_text_prompt_key,
        generated_images_key,
        pre_populated_prompts,
        select_button,
        selected_image_key,
        edit_button,
        title,
        image_to_edit_key,
        download_button,
        auto_submit_first_pre_populated)
    
    if image_to_edit_key in st.session_state:
        render_image_edit_prompt(
            edit_image_prompt_key,
            edited_images_key,
            False,
            image_to_edit_key,
            edit_with_mask,
            mask_image_key,
            select_button,
            selected_image_key,
            download_button)
