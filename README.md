# eventarc-gw

This repo contains an event driven blueprint for how to upload objects from [Google Cloud Storage(GCS)](https://cloud.google.com/storage) to [OpenRelik](https://openrelik.org) and trigger a workflow.

## Before you begin
This blueprint assumes that you have a Google Cloud Project with billing enabled and with the following resources set up:
1. GKE Cluster with [Workload Identity Federation for GKE](https://cloud.google.com/eventarc/standard/docs/gke/route-trigger-cloud-storage#workload-identity) enabled
2. [OpenRelik](https://openrelik.org) installed on your GKE Cluster
3. Deploy the eventarc-gw Deployment and Service
4. GCS Bucket
5. Eventarc Trigger [Cloud Storage Events](https://cloud.google.com/eventarc/standard/docs/gke/route-trigger-cloud-storage)


In your Google Cloud Project enable the following APIs 
```console
gcloud services enable eventarc.googleapis.com \
    eventarcpublishing.googleapis.com \
    iamcredentials.googleapis.com \
    container.googleapis.com \
    cloudresourcemanager.googleapis.com \
    storage.googleapis.com
```

## 1. GKE

Create a GKE Cluster
```console
gcloud container clusters create ${CLUSTER_NAME} \
    --location=${CLUSTER_LOCATION} \
    --workload-pool=${PROJECT_ID}.svc.id.goog
```

Fetch the access credentials
```console
gcloud container clusters get-credentials ${CLUSTER_NAME} --zone ${CLUSTER_LOCATION} --project ${PROJECT_ID}
```

## 2. OpenRelik

### 2.1. Install OpenRelik
The easiest way to install [OpenRelik](https://openrelik.org) on GKE is to apply the Helm Chart available from the [OSDFIR Infrastructure](https://github.com/google/osdifir-infrastructure) repository

Add the repo containing the Helm charts as follows:
```console
helm repo add osdfir-charts https://google.github.io/osdfir-infrastructure
```

Install OpenRelik via the OSDFIR Infrastructure chart using a release name of ```my-release```:
```console
helm install my-release osdfir-charts/osdfir-infrastructure
```

### 2.2. Configure OpenRelik

> [!NOTE]
> You will also need an ```admin``` user to access OpenRelik. Create one using the following command
> 
```console
# Get a terminal in the OpenRelik API Pod
kubectl exec -it deploy/my-release-openrelik-api -- bash

# Create a random password 
password=$(LC_ALL=C tr -dc 'A-Za-z0-9@%*+,-./' < /dev/urandom 2>/dev/null | head -c 16)

# IMPORTANT -> TAKE NOTE OF THIS, you will need it to access OpenRelik in the next steps
echo $password

python admin.py create-user admin --password "$password" --admin 1>/dev/null

# Once the user is created you can exit this shell.
```

### 2.3. Access OpenRelik

OpenRelik is not exposed externally on the GKE Cluster.

For the purpose of this blueprint you can run the following commands from two seperate ```terminals``` on your local machine.

```console
kubectl port-forward service/my-release-openrelik-api 8710:8710 --address='0.0.0.0'
```

```console
kubectl port-forward service/my-release-openrelik 8711:8711 --address='0.0.0.0'
```

You can now point your browser to OpenRelik [http://localhost:8711/](http://localhost:8711/)

Log in using the ```admin``` user and the password you created above and prepare the following 3 things for later use:
1. Create a folder at the root level
2. Create a [reusable workflow template](https://openrelik.org/docs/workflows/#reusable-workflow-templates)
3. Create an API Key (using the user menu at the top right of the screen)

Make sure you export the API Key in the following environment variable for the next step below.
```console
export OPENRELIK_API_KEY=[COPY_YOUR_OPENRELIK_API_KEY_HERE]
```

We will need the ```folder_id``` for the folder you created above. You can retrieve it as following:

Open a tab in the same browser window you are logged in to OpenRelik
[http://localhost:8710/api/v1/folders/](http://localhost:8710/api/v1/folders/)
```
# The output should look similar to this
[
  {
    "id": 2, # <-- this is the folder_id we will need later
    "display_name": "gcs-input",
    "user": {
      "id": 2,
      "display_name": "admin",
      "username": "admin",
      ...
    },
    "selectable": false
  }
]
```

We will also need the ```template_id``` for the reusable workflow template you created above. You can retrieve it as following:

Open a tab in the same browser window you are logged in to OpenRelik
[http://localhost:8710/api/v1/workflows/templates/](http://localhost:8710/api/v1/workflows/templates/)
```
# The output should look similar to this
[
  {
    "id": 1, # <-- this is the template_id we will need later
    "display_name": "demoworkflow",
    ...
  }
]
```

## 3. Deploy the eventarc-gw

### 3.1 Create the OpenRelik API Key Secret
```console
kubectl create secret generic openrelik-api-key --from-literal=api-key="${OPENRELIK_API_KEY}"
```

### 3.2. Apply the eventarc-gw Deployment
```console
kubectl apply -f k8s/deployment-eventarc-gw.yaml
```

### 3.3. Apply the eventarc-gw Service
```console
kubectl apply -f k8s/service-eventarc-gw.yaml
```

## 4. Google Cloud Storage

Create a GCS Bucket
```console
gcloud storage buckets create gs://${GCS_BUCKET}

# Add a label with the OpenRelik folder_id created above 
gcloud storage buckets update gs://${GCS_BUCKET} --update-labels=folder_ID=${OPENRELIK_FOLDER_ID}

# Add a label with the OpenRelik reusable workflow template_id created above 
gcloud storage buckets update gs://${GCS_BUCKET} --update-labels=template_id=${OPENRELIK_WORKFLOW_TEMPLATE_ID}
```

Set up the permissions on the GCS Bucket
```console
# Two roles required by the eventarc-gw pod to access the GCS Bucket and download the event triggering Objects
gcloud storage buckets add-iam-policy-binding gs://${GCS_BUCKET} \
  --member=principal://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${PROJECT_ID}.svc.id.goog/subject/ns/default/sa/default \
  --role=roles/storage.bucketViewer
gcloud storage buckets add-iam-policy-binding gs://${GCS_BUCKET} \
  --member=principal://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${PROJECT_ID}.svc.id.goog/subject/ns/default/sa/default \
  --role=roles/storage.objectUser

# An optional role in case you want to use the GRR GCS Output Plugin to upload objects to the GCS Bucket
gcloud storage buckets add-iam-policy-binding gs://${GCS_BUCKET} \
  --member=principal://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${PROJECT_ID}.svc.id.goog/subject/ns/default/sa/my-release-grr-sa \
  --role=roles/storage.admin
```

## 5. Eventarc

### 5.1. [Prepare the Eventarc Trigger](https://cloud.google.com/eventarc/standard/docs/gke/route-trigger-cloud-storage#preparing)

Create a service account
```console
gcloud iam service-accounts create "event-trigger-sa"
```

Grant the ```pubsub.publisher``` role to the Cloud Storage service account
```console
SERVICE_ACCOUNT="$(gsutil kms serviceaccount -p ${PROJECT_ID})"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/pubsub.publisher"
```

Enable GKE destinations for Eventarc
```console
gcloud eventarc gke-destinations init
```

### 5.2. [Create the Eventarc Trigger](https://cloud.google.com/eventarc/standard/docs/gke/route-trigger-cloud-storage#create-trigger)

```console
gcloud eventarc triggers create eventarc-gw-trigger \
    --location=${REGION} \
    --destination-gke-cluster=${CLUSTER_NAME} \
    --destination-gke-location=${ClUSTER_LOCATION} \
    --destination-gke-namespace=default \
    --destination-gke-service=eventarc-gw \
    --destination-gke-path=/ \
    --event-filters="type=google.cloud.storage.object.v1.finalized" \
    --event-filters="bucket=${GCS_BUCKET}" \
    --service-account="event-trigger-sa@${PROJECT_ID}.iam.gserviceaccount.com"
```

## Test it :-)

You can now upload files to the GCS Bucket and see the Eventarc trigger firing up the ```eventarc-gw```.

The result will be avaialble in OpenRelik at the same path location as you have created in GCS.
