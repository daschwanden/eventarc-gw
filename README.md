# eventarc-gw

This repo contains an event driven blueprint for how to upload objects from [Google Cloud Storage(GCS)](https://cloud.google.com/storage) to [OpenRelik](https://openrelik.org) and trigger a workflow.

## Before you begin
This blueprint assumes that you have a Google Cloud Project with billing enabled and with the following resources set up:
1. A GKE Cluster with [Workload Identity Federation for GKE](https://cloud.google.com/eventarc/standard/docs/gke/route-trigger-cloud-storage#workload-identity) enabled
2. A GCS Bucket
3. An Eventarc Trigger [Cloud Storage Events](https://cloud.google.com/eventarc/standard/docs/gke/route-trigger-cloud-storage)
4. [OpenRelik](https://openrelik.org) installed on your GKE Cluster

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

## 2. Google Cloud Storage

Create a GCS Bucket
```console
gcloud storage buckets create gs://${GCS_BUCKET}
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

## 3. Eventarc

### 3.1. [Prepare the Eventarc Trigger](https://cloud.google.com/eventarc/standard/docs/gke/route-trigger-cloud-storage#preparing)

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

### 3.2. [Create the Eventarc Trigger](https://cloud.google.com/eventarc/standard/docs/gke/route-trigger-cloud-storage#create-trigger)

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

## 4. OpenRelik

The easiest way to install [OpenRelik](https://openrelik.org) on GKE is to apply the Helm Chart available from the [OSDFIR Infrastructure](https://github.com/google/osdifir-infrastructure) repository

Add the repo containing the Helm charts as follows:
```console
helm repo add osdfir-charts https://google.github.io/osdfir-infrastructure
```

Install OpenRelik via the OSDFIR Infrastructure chart using a release name of ```my-release```:
```console
helm install my-release osdfir-charts/osdfir-infrastructure
```

