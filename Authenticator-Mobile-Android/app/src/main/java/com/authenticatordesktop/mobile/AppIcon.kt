package com.authenticatordesktop.mobile

import androidx.compose.foundation.Image
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource

@Composable
internal fun AppIcon(modifier: Modifier = Modifier) {
    Image(painter = painterResource(R.drawable.app_icon), contentDescription = null, modifier = modifier)
}
