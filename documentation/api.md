# Ok Server API

## Introduction

The Ok Server API provides a variety of endpoints to interact with the Ok Server.

> The Base URL is `https://ok.cs61a.org/api/v3/`

## Authentication

Ok uses access tokens to allow access to the API. To obtain a token for a specific account, use the ok-client
to login with your Google account. Download the latest version of ok from the [GitHub Releases](https://github.com/Cal-CS-61A-Staff/ok-client/releases/) or from [cs61a.org/ok](http://cs61a.org/ok)

Then run the following command
`python3 ok --get-token`

```
$ python3 ok --get-token
Please enter your bCourses email.
bCourses email: <optional>
Token: ba23.abcdef...u20a
```

This token gives permission to perform all actions as the user that logged in.

If you are using a browser to perform these requests and are currently logged in, the requests will default to use your account if an access token is not provided.

### Usage

Include the access_token as a parameter in every request to be authenticated.

```
https://ok.cs61a.org/api/v3/endpoint?access_token=ba23.abcdef...w20a
```

Almost all endpoints require authentication. If you are using the `ok-client`, there is a built in method to obtain a user's access token. Otherwise, you can should obtain a user's access token.

### Expiration

Access tokens are short lived (10 minutes - 1 day). Once they expire, you must obtain a new token.

## Client Version
If the `client_version` parameter is included in the URL, the API will respond with a 403 if the version is not up to date with the version on the Ok Admin Dashboard. The URL to download the newest version of the client is included in the response.

# General Endpoints

## API Info
>><h4> Example Response </h4>
```
curl "https://ok.cs61a.org/api/v3/"
{
    "code": 200,
    "message": "success",
    "data": {
        "github": "https://github.com/Cal-CS-61A-Staff/ok",
        "url": "/api/v3/",
        "version": "v3",
        "documentation": "https://okpy.github.io/documentation"
    }
}
```

Info about the V3 API

#### Permissions
No authentication required.

#### HTTP Request
`GET https://ok.cs61a.org/api/v3/version/`

#### Query Parameters
None

## Client Version
>><h4> Example Response </h4>
```
curl "https://ok.cs61a.org/api/v3/version"
{
    "message": "success",
    "data": {
        "results": [
            {
                "name": "ok-client",
                "download_link": "https://github.com/Cal-CS-61A-Staff/ok-client/releases/download/v1.6.14/ok",
                "current_version": "v1.6.14"
            }
        ]
    },
    "code": 200
}
```

Get the current version of OK Clients. Used by the ok-client for autoupdating.
The version is changed in the admin dashboard.

#### Permissions
No authentication required.

#### HTTP Request
`GET https://ok.cs61a.org/api/v3/version`
`GET https://ok.cs61a.org/api/v3/version/<string:client-name>`

#### Query Parameters
If the endpoint is provided with the name of a client in the form of
`GET https://ok.cs61a.org/api/v3/version/name/`, the results will be filtered for clients with that name.
Currently, the only client name used is `ok-client`

#### Response
See example response.

## Enrollment
>><h4> Example Response </h4>
```
curl "https://ok.cs61a.org/api/v3/enrollment/example@gmail.com?access_token=test"
{
    "data": {
        "courses": [
            {
                "course_id": 2,
                "role": "student",
                "class_account": "cs61a-abc",
                "section": "122",
                "course": {
                    "active": true,
                    "offering": "ok/test/su16",
                    "id": 2,
                    "display_name": "OK Sandbox"
                }
            },
        ]
    },
    "code": 200,
    "message": "success"
}
```

Get the courses that a specific user is enrolled in. Used by ok-client to see if a user is enrolled in a course.

#### Permissions
The access_token must belong to the email being requested or be an OK admin.

#### HTTP Request
`GET https://ok.cs61a.org/api/v3/enrollment/<string:email>/`

#### Query Parameters
Parameter | Default | Description
---------- | ------- | -------
access_token | None | (Required) Access Token of staff member

#### Response
See example response.
<!-- End Endpoint -->


# Assignments

## Assignment Info
>><h4> Example Response </h4>
> ```
curl "https://ok.cs61a.org/api/v3/assignment/cal/cs61a/sp16/lab01"
{
    "code": 200,
    "data": {
        "course": {
            "active": true,
            "display_name": "CS 61A",
            "id": 1,
            "offering": "cal/cs61a/sp16"
        },
        "display_name": "Lab 01",
        "due_date": "2016-09-07T06:59:59",
        "files": {
            "fizzbuzz.py": "if ..."
        },
        "max_group_size": 2,
        "name": "cal/cs61a/sp16/lab01",
        "url": null
    },
    "message": "success"
}
```

Get detailed assignment info.

#### Permissions
Requires an access token. The assignment is presented to all staff members of the course or admins but is only shown to other users if the staff marked the assignment as visible .

#### HTTP Request
`GET https://ok.cs61a.org/api/v3/assignment/<assignment_name:endpoint>``

#### Query Parameters
Parameter | Default | Description
---------- | ------- | -------
access_token | None | (Required) Access Token of staff member

#### Response
Name | Type | Description
---------- | -------
due_date | DateTime | UTC Time of deadline in iso8601 format.
files | Dictionary | Template file names and contents
name | String | Endpoint

See example output for other fields.

## Group Info
>><h4> Example Response </h4>
> ```
curl "https://ok.cs61a.org/api/v3/assignment/cal/cs61a/sp16/lab01/group/email@example.com"
{
    "code": 200,
    "data": {
        "members": [
            {
                "created": "2016-08-16T20:54:28",
                "status": "active",
                "updated": null,
                "user": {
                    "email": "email@example.com",
                    "id": "mbk5ez"
                }
            },
            {
                "created": "2016-08-16T20:54:28",
                "status": "pending",
                "updated": null,
                "user": {
                    "email": "okstaff@okpy.org",
                    "id": "nel5aK"
                }
            }
        ]
    },
    "message": "success"
}```

Get detailed assignment info.

#### Permissions
Requires an access token. The group info is presented to all staff members of the course or admins. Otherwise, the access_token must belong to the user whose email is in the URL to get a response.

#### HTTP Request
`GET https://ok.cs61a.org/api/v3/assignment/<assignment_name:endpoint>/group/<string:email>`

#### Query Parameters
Parameter | Default | Description
---------- | ------- | -------
access_token | None | (Required) Access Token of staff member

#### Response
Parameter | Type | Description
---------- | ------- | -------
members | List | List of members if available. If there is no group, this value is equal to `[]`

See example output for fields.
`member['status']` is either "pending" or "active"

## Export Backups
>><h4> Example Response </h4>
> ```
curl "https://ok.cs61a.org/api/v3/assignment/cal/cs61a/sp16/lab00/export/email@berkeley.edu?access_token=test&limit=2&offset=17"
{
    "code": 200,
    "message": "success",
    "data": {
        "count": 2,
        "backups": [
            {
                "messages": [
                    {
                        "contents": {
                            "lab00.py": "def twenty_sixteen(): pass",
                            "submit": true
                        },
                        "kind": "file_contents",
                        "created": "2016-06-26T09:50:31"
                    },
                ],
                "is_late": true,
                "submit": false,
                "created": "2016-06-26T09:50:31"
            },
        ],
        "limit": 2,
        "offset": 1,
        "has_more": false
    }
}
```

Get a single user's backups. This gets all of the backups submitted by a specific user. This endpoint does not retrieve backups from the group that the user is in.
A user is specified through the use of their email in Ok.

#### Permissions
The access_token's user must have permission to view the backup. They must have
at least staff level access to the assignment.

#### HTTP Request
`GET https://ok.cs61a.org/api/v3/assignment/<assignment_name:endpoint>/export/<string:email>`

#### Query Parameters
Parameter | Default | Description
---------- | ------- | -------
access_token | None | (Required) Access Token of staff member
limit | 150 | (Optional) Number of backups to retrieve in one request. High numbers may result in slower responses.
offset | 0 | (Optional) How many recent backups to ignore. An offset of 100 with a limit of 150 will provide backup numbers #101 to #250.

#### Response
Name | Type | Description
---------- | -------
backups | List |  A list of backup objects, sorted by time (most recent to oldest).
has_more | Boolean | Indicates whether this response includes the earliest backup.
count | Integer | The count of total backups from this user
limit | Integer | The value of the limit parameter
offset | Integer | The value of the limit parameter

## Export Final Submissions
>><h4> Example Response </h4>
> ```
curl "https://ok.cs61a.org/api/v3/assignment/cal/cs61a/sp16/lab00/submissions?access_token=test"
{
"message": "success",
"data": {
"backups": [{
    "id": "14a8r3",
    "created": "2016-06-20T12:58:30",
    "submit": true,
    "is_late": false,
    "group": [{ "id": "lejRe2",  "email": "email@berkeley.edu" },
              {"id": "k24k23","email": "email2@berkeley.edu"}],
    "messages": [
        {   "kind": "file_contents",
            "created": "2016-06-20T19:58:30",
            "contents": {
                "lab00.py": "def twenty_sixteen(): pass",
                "submit": true
            }
        },
    ],
    "submitter": {
        "id": "lejRe2",
        "email": "email@berkeley.edu"
    },
    },],
"count": 36,
},
"code": 200
}
```

Get all submissions for a course. This obtains all submissions for an assignment from users that are enrolled in the course.

#### Permissions
The access_token's user must have at least staff level access to the assignment.

#### HTTP Request
`GET https://ok.cs61a.org/api/v3/assignment/<assignment_name:endpoint>/submissions/`

#### Query Parameters
Parameter | Default | Description
---------- | ------- | -------
access_token | None | (Required) Access Token of staff member

#### Response
Name | Type | Description
---------- | -------
backups | List |  A list of backup objects in no particular order
count | Integer | The count of total backups from this user
limit | Integer | Unsupported. Value will be 0
offset | Integer | Unsupported. Value will be 0
has_more | None | Unsupported. Value will be null

# Backups

## Submit a backup
>><h4> Example Request </h4>
> ```python
import requests
data = {
    'assignment': 'cal/cs61a/su16/sample',
    'submit': False,
    'messages': {
        'file_contents': {
            "lab00.py": "def add(x, y): pass"
         }
    }
}
url = "https://ok.cs61a.org/api/v3/backups/?access_token={}"
access_token = 'test'
r = requests.post(url.format(access_token), data=data)
response = r.json()
```
>><h4> Response </h4>
```
{
    "data": {
        "email": "test@berkeley.edu",
        "url": "http://ok.cs61a.org/cal/cs61a/su16/sample/backups/aF249e/",
        "id": "aF249e",
        "course": {
            "id": 1,
            "active": true,
            "display_name": "CS 61A",
            "offering": "cal/cs61a/su16"
        },
        "assignment": "cal/cs61a/su16/sample"
    },
    "code": 200,
    "message": "success"
}
```

Create a new backup or submission.
Used by the ok-client to create a new backup or submission.

#### Permissions
The access_token must be valid. Any student may submit to an assignment, even if they are not enrolled.

#### HTTP Request
`POST https://ok.cs61a.org/api/v3/backups/`

#### Query Parameters
Parameter | Default | Description
---------- | ------- | -------
access_token | None | (Required) Access Token of submitter

#### POST Data Fields
Parameter | Type | Description
---------- | ------- | -------
assignment | String | (Required) Assignment endpoint from staff dashboard
messages | Dictionary | (Required) List of messages to associate with backup.
submit | Boolean | (Optional, Default: False) Whether this is a submission

#### Response
Parameter | Type | Description
---------- | ------- | -------
email | String | The account the backup was created under
key | String | The ID of the backup
url | String | The url to the backup on the OK website
assignment | String | The name of the assignment
course | Dictionary | Course Information

## Create a revision

Creates a backup as a revision. Similiar to Create a Backup

#### HTTP Request
`POST https://ok.cs61a.org/api/v3/revision/`

Same arugments as Create a Backup.

If a user does not have a composition score to revise, the server responds with a 403.

## View a backup
>><h4> Example Response </h4>
> ```
curl "https://ok.cs61a.org/api/v3/backups/aF249e/?access_token=test"
{
    "data": {
        "submitter": { "email": "test@berkeley.edu", "id": "a4r4gd"},
        "submit": false,
        "created": "2016-06-21T03:05:53"
        "group": [
            {"email": "test@berkeley.edu","id": "a4r4gd"}
        ],
        "is_late": false,
        "assignment": {
            "name": "cal/cs61a/su16/sample",
            "course": {"id": 1, "active": true, "display_name": "CS 61A", "offering": "cal/cs61a/su16"}
        },
        "id": "aF249e",
        "messages": [
            {"kind": "file_contents",
             "contents": {
                 "lab00.py": "def add(x, y): pass"
             },
             "created": "2016-06-21T03:05:52"}
        ]
    },
    "code": 200,
    "message": "success"
}
```


View a specific backup

#### Permissions
The access_token must be for a staff member or be for the user who has created the backup. Users who are in the same group as the creator may also view this resource.

#### HTTP Request
`GET https://ok.cs61a.org/api/v3/backups/<string:id>/`

#### Query Parameters
Parameter | Default | Description
---------- | ------- | -------
access_token | None | (Required) Access Token of submitter

#### Response
See example

# Users

## View a specific user

>><h4> Example Response </h4>
> ```
curl "https://ok.cs61a.org/api/v3/user/?access_token=test"
{
    "data": {
        "email": "dschmidt1@gmail.com",
        "id": "penRe7",
        "name": null,
        "participations": [
            {
                "class_account": "cs61a-mbh",
                "course": {
                    "active": true,
                    "display_name": "CS 61A",
                    "id": 1,
                    "offering": "cal/cs61a/sp16",
                    "timezone": "America/Los_Angeles"
                },
                "course_id": 1,
                "role": "student",
                "section": "20"
            }
        ]
    },
    "code": 200,
    "message": "success"
}
```

View a specific user. If the email is not provided, the current users info will be provided. The SID is intentionally not provided.

#### Permissions
The access_token must be for the user whose info is being requested. To view other emails, it must be an admin level access token.

#### HTTP Request
`GET https://ok.cs61a.org/api/v3/user/` (Current User)
`GET https://ok.cs61a.org/api/v3/user/<string:email>`

#### Query Parameters
Parameter | Default | Description
---------- | ------- | -------
access_token | None | (Required) Access Token of submitter

#### Response
See example

# Scores

## Create a score
>><h4> Example Request </h4>
>```python
import requests
data = {
    'bid': 'aF249e',
    'score': 2.0,
    'kind': 'Total',
    'message': 'Test Output:\nTest 1: 2/2.\nGreat Work!'
}
url = 'https://ok.cs61a.org/api/v3/score/?access_token={}'
access_token = 'test'
r = requests.post(url.format(access_token), data=data)
response = r.json()
```
>><h4> Response </h4>
```
{
    "data": {
        "success": True,
        "message": 'OK'
    },
    "code": 200,
    "message": "success"
}
```

Score a backup or submission through the API.

This is used by the server side autograder.

#### HTTP Request
`POST https://ok.cs61a.org/api/v3/score/`

#### Query Parameters
Parameter | Default | Description
---------- | ------- | -------
access_token | None | (Required) Access Token of submitter

#### POST Data Fields
Parameter | Type | Description
---------- | ------- | -------
bid | String | (Required) ID of the Backup
kind | String | (Required) Type of score (for example, Composition)
score | Float | (Required) Score Value
message | String | (Required) Comments to leave about the score

#### Response
Parameter | Type | Description
---------- | ------- | -------
success | Boolean | Whether the score was added
message | String | More details about the success state

# Errors

The Ok API uses the following error codes:
>><h4> Example Response </h4>
> ```
curl "https://ok.cs61a.org/api/v3/404"
{
"message": "The requested URL was not found on the server.
  If you entered the URL manually please check your spelling and try again.
  You have requested this URI [/api/v3/404] but did you mean /api/v3/ or /api/v3/score/ ?",
"data": {},
"code": 404
}
```

Error Code | Meaning
---------- | -------
400 | Bad Request -- Your request was malformed or did not contain all required components.
401 | Unauthorized -- Your access_token was not provided or expired.
403 | Forbidden -- The current token does not have permission to view this resource or there is an error with your request arguments (Client is out of date or this endpoint is not appropriate for the current request)
404 | Not Found -- The specified resource could not be found with your current authentication level.
405 | Method Not Allowed -- The wrong HTTP method was used (for example POST instead of GET)
406 | Not Acceptable -- You requested a format that isn't JSON
410 | Gone -- The resource requested has been removed from our servers
429 | Too Many Requests -- You're making too many API calls!
500 | Internal Server Error -- We had a problem with our server. Try again later. Please file an issue on the ok server github repository.
503 | Service Unavailable -- We're temporarily offline. Please try again later.
