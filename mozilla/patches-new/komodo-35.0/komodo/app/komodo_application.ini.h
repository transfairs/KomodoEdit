#include "nsXREAppData.h"
             static const nsXREAppData sAppData = {
                 sizeof(nsXREAppData),  // size
                 NULL,                  // app directory
                 "ActiveState",         // vendor
                 "Komodo Edit",     // app name

                 NULL,                  // remote app name (NULL means same as app name)

                 "12.0.1",       // app version
                 "18513",  // buildID
                 "{b1042fb5-9e9c-11db-b107-000d935d3368}", // app guid
                 "Copyright (c) 1999 - 2026 ActiveState", // copyright
                 14,                    // flags (PROFILE_MIGRATOR | EXTENSION_MANAGER | CRASH_REPORTER)
                 NULL,                  // xreDirectory
                 "35.0", // XRE minVersion
                 "35.0", // XRE maxVersion
                 "https://komodo.activestate.com/crash/submit", // crash report
                 NULL                   // profile directory

                 ,
                 NULL                   // user agent string

             };
