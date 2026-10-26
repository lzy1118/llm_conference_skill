package org.grobid.core.utilities;

import static org.hamcrest.CoreMatchers.is;
import static org.hamcrest.MatcherAssert.assertThat;
import static org.junit.Assert.assertEquals;

import java.util.ArrayList;

import com.google.common.collect.Lists;
import org.junit.Ignore;
import org.junit.Test;

import org.grobid.core.test.EngineTest;

@Ignore
public class UnicodeUtilTest extends EngineTest {

    @Test
    public void testNormaliseToken() throws Exception {
        String test = "´\rÓÑÔÙØØØ";
        String result = UnicodeUtil.normaliseText(test);
        assertThat("´\nÓÑÔÙØØØ", is(result));

        ArrayList<String> tokens = Lists.newArrayList(
                "½ºº´\r",
                "½ºº´\n",
                "½ºº´\t",
                "½ºº´\f",
                "½ºº´ ",
                "½ºº´\f\n",
                "½ºº´\r\t");
        for (String token : tokens) {
            assertEquals("½ºº´", UnicodeUtil.normaliseText(token.replace(" ", "").replace("\n", "")));
        }
    }

}
