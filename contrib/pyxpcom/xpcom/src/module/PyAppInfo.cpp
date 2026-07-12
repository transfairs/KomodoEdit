#include "PyAppInfo.h"

#include "nsIFile.h"
#include "nsCOMPtr.h"
#include "nsStringGlue.h"
#include "nsXULAppAPI.h"

#ifdef XP_UNIX
#include <unistd.h>
#endif

#ifdef XP_WIN
#include <windows.h>
#include <process.h>
#endif

// This leaks. But we can't do much about that.
static PyAppInfo* gAppInfo = nullptr;

NS_IMPL_ISUPPORTS(PyAppInfo,
                  nsIXULAppInfo,
                  nsIXULRuntime,
                  nsIFactory)

PyAppInfo::PyAppInfo(nsIFile* aAppDir) :
    mLogConsoleErrors(false),
    mLoadedXULFuncs(XULFUNCS_UNINITIALIZED)
{
    memset(&mAppData, 0, sizeof(mAppData));
    if (!aAppDir) {
        return;
    }
    nsresult rv;
    nsCOMPtr<nsIFile> appIni;
    rv = aAppDir->Clone(getter_AddRefs(appIni));
    if (NS_FAILED(rv)) {
        return;
    }
    rv = appIni->Append(NS_LITERAL_STRING("application.ini"));
    if (NS_FAILED(rv)) {
        return;
    }
    bool exists;
    rv = appIni->Exists(&exists);
    if (NS_FAILED(rv) || !exists) {
        return;
    }
    if (!EnsureXULFuncs()) {
        return;
    }
    rv = XRE_ParseAppData(appIni, &mAppData);
    if (NS_FAILED(rv)) {
        return;
    }
    NS_ADDREF(mAppData.directory = aAppDir);


}

PyAppInfo::~PyAppInfo() {
}

/* static */
PyAppInfo* PyAppInfo::GetSingleton(nsIFile* aAppDir) {
    if (!gAppInfo) {
        gAppInfo = new PyAppInfo(aAppDir);
    }
    return gAppInfo;
}

bool PyAppInfo::EnsureXULFuncs() {
    if (mLoadedXULFuncs == XULFUNCS_UNINITIALIZED) {
        const struct nsDynamicFunctionLoad kXULFuncs[] = {
                {"XRE_GetProcessType", (NSFuncPtr*) &XRE_GetProcessType},
                {"XRE_ParseAppData", (NSFuncPtr*) &XRE_ParseAppData},
                {nullptr, nullptr },
        };
        nsresult rv = XPCOMGlueLoadXULFunctions(kXULFuncs);
        mLoadedXULFuncs = (rv == NS_OK) ? XULFUNCS_LOADED : XULFUNCS_FAILED;
    }
    return (mLoadedXULFuncs == XULFUNCS_LOADED);
}

/* readonly attribute ACString vendor; */
NS_IMETHODIMP
PyAppInfo::GetVendor(nsACString & aVendor)
{
    if (!mAppData.vendor || !*mAppData.vendor) {
        aVendor.SetIsVoid(true);
    } else {
        aVendor.Assign(mAppData.vendor);
    }
    return NS_OK;
}

/* readonly attribute ACString name; */
NS_IMETHODIMP
PyAppInfo::GetName(nsACString & aName)
{
    if (!mAppData.name || !*mAppData.name) {
        return NS_ERROR_FAILURE;
    }
    aName.Assign(mAppData.name);
    return NS_OK;
}

/* readonly attribute ACString ID; */
NS_IMETHODIMP
PyAppInfo::GetID(nsACString & aID)
{
    if (!mAppData.ID || !*mAppData.ID) {
        aID.SetIsVoid(true);
    } else {
        aID.Assign(mAppData.ID);
    }
    return NS_OK;
}

/* readonly attribute ACString version; */
NS_IMETHODIMP
PyAppInfo::GetVersion(nsACString & aVersion)
{
    if (!mAppData.version || !*mAppData.version) {
        aVersion.SetIsVoid(true);
    } else {
        aVersion.Assign(mAppData.version);
    }
    return NS_OK;
}

/* readonly attribute ACString appBuildID; */
NS_IMETHODIMP
PyAppInfo::GetAppBuildID(nsACString & aAppBuildID)
{
    if (!mAppData.buildID) {
        aAppBuildID.SetIsVoid(true);
    } else {
        aAppBuildID.Assign(mAppData.buildID);
    }
    return NS_OK;
}

/* readonly attribute ACString platformVersion; */
NS_IMETHODIMP
PyAppInfo::GetPlatformVersion(nsACString & aPlatformVersion)
{
    aPlatformVersion.AssignLiteral(NS_STRINGIFY(GRE_MILESTONE));
    return NS_OK;
}

/* readonly attribute ACString platformBuildID; */
NS_IMETHODIMP
PyAppInfo::GetPlatformBuildID(nsACString & aPlatformBuildID)
{
    aPlatformBuildID.AssignLiteral(NS_STRINGIFY(GRE_BUILDID));
    return NS_OK;
}

/* readonly attribute ACString UAName; */
NS_IMETHODIMP
PyAppInfo::GetUAName(nsACString & aUAName)
{
    if (!mAppData.UAName) {
        aUAName.SetIsVoid(true);
    } else {
        aUAName.Assign(mAppData.UAName);
    }
    return NS_OK;
}

/* readonly attribute boolean inSafeMode; */
NS_IMETHODIMP
PyAppInfo::GetInSafeMode(bool *aInSafeMode)
{
    // We don't have a concept of safe mode
    NS_ENSURE_ARG_POINTER(aInSafeMode);
    *aInSafeMode = false;
    return NS_OK;
}

/* attribute boolean logConsoleErrors; */
NS_IMETHODIMP
PyAppInfo::GetLogConsoleErrors(bool *aLogConsoleErrors)
{
    NS_ENSURE_ARG_POINTER(aLogConsoleErrors);
    *aLogConsoleErrors = mLogConsoleErrors;
    return NS_OK;
}
NS_IMETHODIMP
PyAppInfo::SetLogConsoleErrors(bool aLogConsoleErrors)
{
    mLogConsoleErrors = aLogConsoleErrors;
    return NS_OK;
}

/* readonly attribute AUTF8String OS; */
NS_IMETHODIMP
PyAppInfo::GetOS(nsACString & aOS)
{
    aOS.AssignLiteral(NS_STRINGIFY(OS_ARCH));
    return NS_OK;
}

/* readonly attribute AUTF8String XPCOMABI; */
NS_IMETHODIMP
PyAppInfo::GetXPCOMABI(nsACString & aXPCOMABI)
{
    if (sizeof(NS_STRINGIFY(TARGET_XPCOM_ABI) "") <= 1) {
      return NS_ERROR_NOT_AVAILABLE;
    }
    aXPCOMABI.AssignLiteral(NS_STRINGIFY(TARGET_XPCOM_ABI));
    return NS_OK;
}

/* readonly attribute AUTF8String widgetToolkit; */
NS_IMETHODIMP
PyAppInfo::GetWidgetToolkit(nsACString & aWidgetToolkit)
{
    /* MOZ_WIDGET_TOOLKIT is not set by configure, so not implemented for now.
    if (sizeof(NS_STRINGIFY(MOZ_WIDGET_TOOLKIT) "") <= 1) {
      return NS_ERROR_NOT_AVAILABLE;
    }
    aWidgetToolkit.AssignLiteral(NS_STRINGIFY(MOZ_WIDGET_TOOLKIT));
    return NS_OK;
    */
    return NS_ERROR_NOT_IMPLEMENTED;
}

/* readonly attribute unsigned long processType; */
NS_IMETHODIMP
PyAppInfo::GetProcessType(uint32_t *aProcessType)
{
    NS_ENSURE_ARG_POINTER(aProcessType);
    NS_ENSURE_TRUE(EnsureXULFuncs(), NS_ERROR_NOT_INITIALIZED);
    *aProcessType = XRE_GetProcessType();
    return NS_OK;
}

/* readonly attribute unsigned long processID; */
NS_IMETHODIMP
PyAppInfo::GetProcessID(uint32_t* aResult)
{
#ifdef XP_WIN
  *aResult = GetCurrentProcessId();
#else
  *aResult = getpid();
#endif
  return NS_OK;
}

/* readonly attribute boolean browserTabsRemoteAutostart; */
NS_IMETHODIMP
PyAppInfo::GetBrowserTabsRemoteAutostart(bool* aResult)
{
    // We don't support remote browser tabs (multiprocess browsers).
    *aResult = false;
    return NS_OK;
}

/* readonly attribute boolean accessibilityEnabled; */
NS_IMETHODIMP
PyAppInfo::GetAccessibilityEnabled(bool* aResult)
{
    // We don't support accessibility
    *aResult = false;
    return NS_OK;
}

/* readonly attribute boolean keyboardMayHaveIME; */
NS_IMETHODIMP
PyAppInfo::GetKeyboardMayHaveIME(bool* aResult)
{
    // We don't support it
    *aResult = false;
    return NS_OK;
}

/* readonly attribute boolean isReleaseBuild; */
NS_IMETHODIMP
PyAppInfo::GetIsReleaseBuild(bool* aResult)
{
#ifdef RELEASE_BUILD
    *aResult = true;
#else
    *aResult = false;
#endif
    return NS_OK;
}

/* readonly attribute boolean isOfficialBranding; */
NS_IMETHODIMP
PyAppInfo::GetIsOfficialBranding(bool* aResult)
{
#ifdef MOZ_OFFICIAL_BRANDING
  *aResult = true;
#else
  *aResult = false;
#endif
  return NS_OK;
}

/* readonly attribute boolean isOfficial; */
NS_IMETHODIMP
PyAppInfo::GetIsOfficial(bool* aResult)
{
#ifdef MOZ_OFFICIAL
  *aResult = true;
#else
  *aResult = false;
#endif
  return NS_OK;
}

/* readonly attribute AUTF8String defaultUpdateChannel; */
NS_IMETHODIMP
PyAppInfo::GetDefaultUpdateChannel(nsACString& aResult)
{
  aResult.AssignLiteral(NS_STRINGIFY(MOZ_UPDATE_CHANNEL));
  return NS_OK;
}

/* readonly attribute AUTF8String distributionID; */
NS_IMETHODIMP
PyAppInfo::GetDistributionID(nsACString& aResult)
{
  aResult.AssignLiteral(MOZ_DISTRIBUTION_ID);
  return NS_OK;
}

/* void invalidateCachesOnRestart (); */
NS_IMETHODIMP
PyAppInfo::InvalidateCachesOnRestart()
{
    // We don't have a profile to put caches in
    return NS_OK;
}

/* void ensureContentProcess (); */
NS_IMETHODIMP
PyAppInfo::EnsureContentProcess()
{
    return NS_ERROR_NOT_IMPLEMENTED;
}

/* readonly attribute PRTime replacedLockTime; */
NS_IMETHODIMP
PyAppInfo::GetReplacedLockTime(PRTime *aReplacedLockTime)
{
    return NS_ERROR_NOT_IMPLEMENTED;
}

/* readonly attribute DOMString lastRunCrashID; */
NS_IMETHODIMP
PyAppInfo::GetLastRunCrashID(nsAString & aLastRunCrashID)
{
    return NS_ERROR_NOT_IMPLEMENTED;
}

/* void createInstance (in nsISupports aOuter, in nsIIDRef iid, [iid_is (iid), retval] out nsQIResult result); */
NS_IMETHODIMP
PyAppInfo::CreateInstance(nsISupports *aOuter, const nsIID & iid, void **result)
{
    NS_ENSURE_NO_AGGREGATION(aOuter);
    // We are our own singleton.
    return QueryInterface(iid, result);
}

/* void lockFactory (in boolean lock); */
NS_IMETHODIMP
PyAppInfo::LockFactory(bool lock)
{
    return NS_ERROR_NOT_IMPLEMENTED;
}
